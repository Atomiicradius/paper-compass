"""An OPTIONAL LLM explanation of an evidence chain, with the template summary as a safe fallback.

The template summary (rag/summary.py) stays the default. When the LLM option is on, the model gets ONLY the evidence
(counts, paper ids, titles, years, source sentences) and a few rules, and its answer is accepted only if it passes
three guardrails. If anything goes wrong (no key, no network, an API or rate-limit error, a timeout, or a failed
check) the template summary is returned instead and the result says why.

    explanation_text(evidence, use_llm=None, complete=None)
        -> {"text", "source": "llm" | "template", "fallback_reason", ...}

Providers, behind one small interface (a function that takes the prompt text and returns the model's text):
    "gemini"     google-genai SDK         key in GEMINI_API_KEY
    "anthropic"  anthropic SDK            key in ANTHROPIC_API_KEY
Settings come from environment variables, or from the gitignored .env file at the repository root (environment
variables win). The key is never logged, printed or put into a result; error details have it scrubbed out.

    PC_LLM_SUMMARY=1       turn the option on (default: off, template)
    PC_LLM_PROVIDER        gemini (default) or anthropic
    PC_LLM_MODEL           model name; default per provider (DEFAULT_MODELS below)
    PC_LLM_TEMPERATURE     optional; sent only if set (see the note on temperature below)

The SDKs are imported only when a call is made, so importing this module needs neither.
"""
import hashlib
import json
import os
import re
import threading
import time
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path

from .citations import verify_citations
from .evidence import collect_paper_ids
from .summary import _clean, summarize_evidence

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"  # gitignored (the root .gitignore ignores every file named .env)
# Cache of generated summaries: one small JSON file per (provider, model, prompt). The folder is under data/, which the root
# .gitignore ignores (git check-ignore -v data/llm_cache/x.json). PC_LLM_CACHE=0 turns the cache off.
CACHE_DIR = REPO_ROOT / "data" / "llm_cache"

PROVIDERS = ("gemini", "anthropic")
KEY_VARIABLES = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
# Defaults checked in the providers' official documentation on 2026-11-21:
#   gemini    "gemini-3.8-flash"  model page https://aistudio.google.com/docs/models/gemini-3.8-flash (ai.google.dev
#             redirects there): "Model code gemini-3.8-flash", "Stable: gemini-3.8-flash".
#   anthropic "claude-haiku-5-5"  https://platform.claude.com/docs/en/models/haiku-5-5/overview : "Model ID:
#             claude-haiku-5-5", status "Active (latest)", retirement "not sooner than October 7, 2027".
DEFAULT_MODELS = {"gemini": "gemini-3.8-flash", "anthropic": "claude-haiku-5-5"}
# The two pages say that these models do not use a custom temperature: the Gemini docs say "Gemini 4 and Gemini
# 3.6+ models ignore custom values for temperature, top_p, and top_k"; the Claude Haiku 5.5 page says "Omit
# temperature, top_p, and top_k". So temperature is NOT sent unless PC_LLM_TEMPERATURE is set (for another model).
MAX_OUTPUT_TOKENS = 600
TIMEOUT_SECONDS = 20  # the default; PC_LLM_TIMEOUT_S (5 to 120) changes it
TIMEOUT_RANGE = (5, 120)
# Gemini thinking (PC_LLM_THINKING, Gemini only, off by default = the setting is not sent). Documented on
# https://aistudio.google.com/docs/thinking (generateContent version) and on the model page
# https://aistudio.google.com/docs/models/gemini-3.8-flash : "Thinking: Supported (low, medium, high)", "minimal is not
# supported and returns an error", and thinking cannot be switched off for this model; the SDK option is
# types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low")). max_output_tokens includes the
# thinking tokens, so a low level leaves more of the 600 tokens for the answer.
THINKING_LEVELS = ("low", "medium", "high")

# Phrases the explanation must not contain (matched case-insensitively, whole words where it matters).
FORBIDDEN_PATTERNS = (r"no one has", r"never been", r"\bfirst to\b",
                      # also from AGENTS.md ("wording rules")
                      r"definitely unexplored", r"guaranteed", r"nobody has done")
# "proven gap" and "proven research gap" are allowed ONLY right after a negation in the same clause ("is not a proven
# research gap", "not proof of a proven gap", "no proven gap"); every other use is rejected.
PROVEN_GAP = re.compile(r"proven (?:research )?gap")
NEGATIONS = {"not", "no", "isn't", "aren't", "wasn't", "weren't", "isnt"}
CLAUSE_END = re.compile(r"[.;:!?,\n]")
NEGATION_WINDOW = 4  # words before the phrase that may hold the negation ("not proof of a")


def affirmative_proven_gap(text):
    """The first use of "proven gap" / "proven research gap" that is NOT negated, as written, else None. A use is
    negated if one of the NEGATION_WINDOW words before it, inside the same clause, is a negation word."""
    lowered = text.lower().replace("’", "'")
    for found in PROVEN_GAP.finditer(lowered):
        clause = CLAUSE_END.split(lowered[:found.start()])[-1]
        words = re.findall(r"[a-z']+", clause)[-NEGATION_WINDOW:]
        if not NEGATIONS.intersection(words):
            return found.group(0)
    return None

FALLBACK_REASONS = ("no key", "error", "timeout", "rate limit", "citation check", "number check", "forbidden phrase")
# The SDKs get the timeout themselves and no automatic retries, so a slow call is cancelled by the SDK. The outer guard
# (a daemon thread, so it can never keep the process alive) only waits this much longer, as a last resort.
GUARD_GRACE_SECONDS = 5

RULES = """You explain ONE pair of research elements (A and B) to a human reviewer, using ONLY the EVIDENCE below.
Rules:
1. Write exactly 2 short paragraphs. The first starts with the line "What the corpus shows" and gives observations
   only (counts, years). The second starts with the line "What the system infers" and gives the inference in
   cautious wording.
2. Every statement about a paper carries that paper's marker exactly as written in the evidence, for example
   [paper:W123]. Mention only papers listed in the evidence.
3. Use only numbers that appear in the evidence, or a rounding of one (for example 4.04 or 4.0), or the percent
   form of a ratio that appears in it. Do not compute new numbers.
4. If the inference is that the pair is rarely seen, say "potentially underexplored in the analyzed corpus". Never
   write "proven gap", never claim that something is new, unexplored for certain, or that nobody has done it.
5. Say that the counts depend on the extraction and on the analyzed corpus.
6. Do not add facts that are not in the evidence."""


# --- settings ------------------------------------------------------------------------------------

def read_env_file(path=None):
    """KEY=VALUE lines of a .env file as a dict (comments and blank lines skipped, quotes stripped). {} if missing.
    path=None means ENV_FILE, looked up at call time (so a test can point it somewhere else)."""
    values = {}
    try:
        text = Path(ENV_FILE if path is None else path).read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def setting(name, env=None, env_file=None):
    """A setting from the environment, else from the .env file, else None. Empty values count as unset."""
    import os
    source = os.environ if env is None else env
    value = source.get(name) or read_env_file(env_file).get(name)
    return value or None


def timeout_setting(env=None, env_file=None):
    """PC_LLM_TIMEOUT_S in seconds (5 to 120), or the default of 20. Raises ValueError for anything else."""
    raw = setting("PC_LLM_TIMEOUT_S", env, env_file)
    if raw is None:
        return TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"PC_LLM_TIMEOUT_S must be a number from {TIMEOUT_RANGE[0]} to {TIMEOUT_RANGE[1]}, got {raw!r}") from None
    if not TIMEOUT_RANGE[0] <= value <= TIMEOUT_RANGE[1]:  # also false for nan
        raise ValueError(f"PC_LLM_TIMEOUT_S must be between {TIMEOUT_RANGE[0]} and {TIMEOUT_RANGE[1]} seconds, got {raw!r}")
    return int(value) if value == int(value) else value


def thinking_setting(env=None, env_file=None):
    """PC_LLM_THINKING: None (not set: nothing is sent) or one of THINKING_LEVELS. Raises ValueError otherwise."""
    raw = setting("PC_LLM_THINKING", env, env_file)
    if raw is None:
        return None
    level = raw.strip().lower()
    if level not in THINKING_LEVELS:
        raise ValueError(f"PC_LLM_THINKING must be one of {', '.join(THINKING_LEVELS)} (gemini-3.8-flash does not support "
                         f"'minimal' or switching thinking off), got {raw!r}")
    return level


def llm_enabled(env=None, env_file=None):
    return setting("PC_LLM_SUMMARY", env, env_file) == "1"


# --- the prompt ----------------------------------------------------------------------------------

def _expected(value):
    return f"{value:.2f}"


def evidence_text(evidence):
    """The evidence as plain text. This is everything the model is told about the data, and the reference the
    number check uses."""
    a, b = evidence["pair"]["a"], evidence["pair"]["b"]
    c = evidence["corpus"]
    lines = [f'A = {a["kind"]} "{_clean(a["name"])}"', f'B = {b["kind"]} "{_clean(b["name"])}"',
             f"cutoff year: {c['cutoff_year']}",
             f"papers in the analyzed corpus (both a {a['kind']} and a {b['kind']} extracted): {c['universe_size']}",
             f"papers using A: {c['n_a']}", f"papers using B: {c['n_b']}",
             f"papers using A and B together in one experiment (observed): {c['observed']}",
             f"expected together if A and B were combined independently: {_expected(c['expected'])}"]
    if evidence["yearly"]:
        series = "; ".join(f"{y['year']}: {y['a']} using A, {y['b']} using B, {y['both']} using both"
                           for y in evidence["yearly"][-3:])
        lines.append(f"papers per year, most recent years: {series}")
    names = {"supports_A": "papers that use A but not B", "supports_B": "papers that use B but not A",
             "bridge": "bridge papers (cite into or between the two sets)",
             "nearest_existing": "nearest existing work"}
    for role, label in names.items():
        entries = evidence["roles"].get(role, [])
        if not entries:
            continue
        lines.append(f"{label}:")
        for e in entries:
            line = f"- [paper:{e['paper_id']}] {_clean(e['title'])} ({e['year']})"
            if e.get("tier"):
                line += f", {e['tier']} match"
                if e.get("similarity") is not None:
                    line += f", embedding similarity {e['similarity']:.2f}"
                if e.get("uses"):
                    line += f", uses {e['uses']}"
            lines.append(line)
            if e.get("source_sentence"):
                lines.append(f'  source sentence: "{_clean(e["source_sentence"])}"')
    lines.append("limitations:")
    lines.extend(f"- {_clean(item)}" for item in evidence.get("limitations", []))
    return "\n".join(lines)


def build_prompt(evidence):
    """The full prompt: the rules and the evidence, nothing else."""
    return f"{RULES}\n\nEVIDENCE\n{evidence_text(evidence)}\n"


# --- guardrails ----------------------------------------------------------------------------------

NUMBER = re.compile(r"\d+(?:\.\d+)?")
MARKER = re.compile(r"\[paper:[^\[\]\s]+\]")


def numbers_in(text):
    """Numbers in a text, ignoring the ids inside [paper:...] markers."""
    return set(NUMBER.findall(MARKER.sub(" ", text)))


def explained_values(evidence_numbers):
    """Every value a number in the answer may have, given the numbers (as text) found in the evidence: the number
    itself; its rounding to 0, 1 or 2 decimals (half up or half to even); and, for a ratio (a number from 0 to 1
    written with decimals, such as an embedding similarity), the percent form 100 * ratio rounded the same ways."""
    allowed = set()
    for token in evidence_numbers:
        value = Decimal(token)
        allowed.add(value)
        bases = [value]
        if "." in token and Decimal(0) <= value <= Decimal(1):
            bases.append(value * 100)
        for base in bases:
            for places in (0, 1, 2):
                for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN):
                    allowed.add(base.quantize(Decimal(1).scaleb(-places), rounding=mode))
    return allowed


def unexplained_numbers(text, evidence_text_value):
    """The numbers of `text` (ids inside [paper:...] markers ignored) that are neither a number of the evidence text
    nor a rounding or percent form of one (see explained_values). Sorted, as written."""
    allowed = explained_values(numbers_in(evidence_text_value))
    return sorted((t for t in numbers_in(text) if Decimal(t) not in allowed), key=float)


def check_output(text, evidence):
    """The three guardrails. Returns (None, "") if the text passes, else (reason, detail)."""
    result = verify_citations(text, collect_paper_ids(evidence))
    if not result["ok"]:
        parts = []
        if result["unknown"]:
            parts.append(f"cites papers that are not in the evidence: {', '.join(result['unknown'])}")
        if result["uncited_markers_count"]:
            parts.append(f"{result['uncited_markers_count']} malformed marker(s)")
        return "citation check", "; ".join(parts)
    invented = unexplained_numbers(text, evidence_text(evidence))
    if invented:
        return "number check", f"numbers that are not in the evidence or a rounding of one: {', '.join(invented)}"
    lowered = text.lower()
    for pattern in FORBIDDEN_PATTERNS:
        found = re.search(pattern, lowered)
        if found:
            return "forbidden phrase", f"contains {found.group(0)!r}"
    phrase = affirmative_proven_gap(text)
    if phrase:
        return "forbidden phrase", f"contains {phrase!r} without a negation right before it"
    return None, ""


# --- providers -----------------------------------------------------------------------------------

def gemini_client(api_key, model, max_output_tokens=MAX_OUTPUT_TOKENS, temperature=None, timeout=TIMEOUT_SECONDS,
                  attempt_log=None, base_url=None, thinking_level=None):
    """A function prompt -> text using the official google-genai SDK.

    Options (documented in the SDK's own field descriptions, google/genai/types.py, google-genai 3.6.1):
      HttpOptions(timeout=...)                    "Timeout for the request in milliseconds."
      HttpOptions(retry_options=HttpRetryOptions(attempts=1))
                                                  attempts: "Maximum number of attempts, including the original request.
                                                  If 0 or 1, it means no retries. If not specified, default to 5."
    attempt_log, if given, gets one entry per HTTP request the SDK sends (a request event hook), so retries are visible.
    thinking_level (None = not sent) goes into GenerateContentConfig(thinking_config=ThinkingConfig(thinking_level=...)).
    base_url is only for tests that point the SDK at a local server."""
    from google import genai
    from google.genai import types

    options = {"timeout": int(round(float(timeout) * 1000)), "retry_options": types.HttpRetryOptions(attempts=1)}
    if base_url:
        options["base_url"] = base_url
    if attempt_log is not None:
        options["client_args"] = {"event_hooks": {"request": [lambda request: attempt_log.append(1)]}}
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(**options))

    def complete(prompt):
        arguments = {"max_output_tokens": max_output_tokens}
        if temperature is not None:
            arguments["temperature"] = temperature
        if thinking_level is not None:
            arguments["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
        response = client.models.generate_content(model=model, contents=prompt,
                                                  config=types.GenerateContentConfig(**arguments))
        return response.text

    return complete


def anthropic_client(api_key, model, max_tokens=MAX_OUTPUT_TOKENS, timeout=TIMEOUT_SECONDS, temperature=None):
    """A function prompt -> text using the official anthropic SDK. Options (platform.claude.com/docs/en/api/sdks/python):
    the client option `timeout` in seconds (a float) and `max_retries` (0 here; the SDK default is 2)."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, timeout=float(timeout), max_retries=0)

    def complete(prompt):
        arguments = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if temperature is not None:
            arguments["temperature"] = temperature
        message = client.messages.create(**arguments)
        return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")

    return complete


def make_client(provider, api_key, model, temperature=None, timeout=TIMEOUT_SECONDS, attempt_log=None,
                thinking_level=None):
    if provider == "gemini":
        return gemini_client(api_key, model, temperature=temperature, timeout=timeout, attempt_log=attempt_log,
                             thinking_level=thinking_level)
    return anthropic_client(api_key, model, temperature=temperature, timeout=timeout)


# --- cache of generated summaries ----------------------------------------------------------------

def cache_key(provider, model, prompt):
    """sha256 of (provider, model, prompt text): the same question to the same model."""
    return hashlib.sha256(json.dumps([provider, model, prompt], ensure_ascii=False).encode("utf-8")).hexdigest()


def cache_get(directory, key):
    """The stored text for a key, or None (missing, unreadable or malformed files count as a miss)."""
    try:
        data = json.loads((Path(directory) / f"{key}.json").read_text(encoding="utf-8"))
        return data["text"] if isinstance(data.get("text"), str) else None
    except (OSError, ValueError, AttributeError, KeyError):
        return None


def cache_put(directory, key, provider, model, text):
    """Store a text that passed the guardrails (written to a temporary file first, so a half-written file is never read)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{key}.json"
    temporary = directory / f"{key}.json.tmp"
    temporary.write_text(json.dumps({"provider": provider, "model": model, "text": text}, ensure_ascii=False),
                         encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def cache_delete(directory, key):
    try:
        (Path(directory) / f"{key}.json").unlink()
    except OSError:
        pass


# --- running a call safely -----------------------------------------------------------------------

def _scrub(text, secret):
    text = " ".join(str(text).split())
    if secret:
        text = text.replace(secret, "***")
    return text[:300]


def _is_rate_limit(exc):
    return (type(exc).__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429
            or getattr(exc, "code", None) == 429)


TIMEOUT_NAMES = {"APITimeoutError", "TimeoutError", "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout",
                 "TimeoutException"}


def _is_timeout(exc):
    return any(cls.__name__ in TIMEOUT_NAMES for cls in type(exc).__mro__)


def _call_with_timeout(complete, prompt, seconds):
    """Run complete(prompt) in a DAEMON thread and wait at most `seconds`. For the real SDK clients this is only a last
    resort: the SDK has its own timeout and no retries, so it cancels the request and the thread ends by itself. A
    daemon thread never keeps the process from exiting, even if a call were stuck."""
    box = {}

    def run():
        try:
            box["text"] = complete(prompt)
        except BaseException as exc:  # noqa: BLE001 - handed to the caller
            box["error"] = exc

    thread = threading.Thread(target=run, name="llm-call", daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"no answer within {seconds} s")
    if "error" in box:
        raise box["error"]
    return box.get("text")


def template_result(evidence, reason, detail="", **extra):
    return {"text": summarize_evidence(evidence), "source": "template", "fallback_reason": reason,
            "detail": detail, **extra}


def explanation_text(evidence, use_llm=None, complete=None, provider=None, model=None,
                     timeout_seconds=None, env=None, env_file=None, cache_dir=None):
    """The explanation for an evidence chain: {text, source, fallback_reason, detail, ...}.

    use_llm: None follows PC_LLM_SUMMARY (default off = template); True or False overrides it. complete is an
    optional function prompt -> text used instead of a real provider (tests pass fakes; no key is needed then).
    source is "llm" only when the model's text passed the guardrails; otherwise it is "template" and
    fallback_reason says why: None (the option was off) or one of FALLBACK_REASONS. detail has the specifics (never
    the key); provider, model and latency_ms are added when a call was made.

    Cache: with a real provider, a text that passed the guardrails is stored under CACHE_DIR, keyed by a hash of
    (provider, model, prompt), and a later identical request reads it instead of calling the API (result key "cache":
    "hit", "miss" or "off"). The guardrails run on a cached text every time, and a cached text that no longer passes is
    deleted and the template is returned. Failures and fallbacks are never stored. PC_LLM_CACHE=0 turns it off. With a
    caller-supplied `complete` (tests) the cache is used only if cache_dir is given.
    """
    if use_llm is None:
        use_llm = llm_enabled(env, env_file)
    if not use_llm:
        return {"text": summarize_evidence(evidence), "source": "template", "fallback_reason": None, "detail": ""}

    try:
        if timeout_seconds is None:  # an explicit argument wins over PC_LLM_TIMEOUT_S
            timeout_seconds = timeout_setting(env, env_file)
        thinking_level = thinking_setting(env, env_file)
    except ValueError as exc:
        return template_result(evidence, "error", str(exc))
    provider = provider or setting("PC_LLM_PROVIDER", env, env_file) or "gemini"
    if provider not in PROVIDERS:
        return template_result(evidence, "error", f"unknown provider {provider!r}; use one of {', '.join(PROVIDERS)}")
    model = model or setting("PC_LLM_MODEL", env, env_file) or DEFAULT_MODELS[provider]
    info = {"provider": provider, "model": model, "timeout_s": timeout_seconds}
    if provider == "gemini" and thinking_level:
        info["thinking"] = thinking_level
    key = None
    attempt_log = []
    guard = timeout_seconds
    prompt = build_prompt(evidence)
    cache_on = setting("PC_LLM_CACHE", env, env_file) != "0" and (complete is None or cache_dir is not None)
    directory = Path(cache_dir) if cache_dir is not None else Path(CACHE_DIR)
    ckey = cache_key(provider, model, prompt)
    info["cache"] = "off"
    if cache_on:
        info["cache"] = "miss"
        cached = cache_get(directory, ckey)
        if cached is not None:
            reason, detail = check_output(cached, evidence)  # the guardrails run on every hit
            if reason:
                cache_delete(directory, ckey)
                return template_result(evidence, reason, f"{detail} (cached text, removed from the cache)",
                                       rejected_text=cached, **{**info, "cache": "hit, rejected"})
            return {"text": cached.strip(), "source": "llm", "fallback_reason": None, "detail": "", "latency_ms": 0,
                    **{**info, "cache": "hit"}}
    if complete is None:
        key = setting(KEY_VARIABLES[provider], env, env_file)
        if not key:
            return template_result(evidence, "no key", f"{KEY_VARIABLES[provider]} is not set", **info)
        temperature = setting("PC_LLM_TEMPERATURE", env, env_file)
        try:
            complete = make_client(provider, key, model, float(temperature) if temperature else None,
                                   timeout=timeout_seconds, attempt_log=attempt_log,
                                   thinking_level=thinking_level if provider == "gemini" else None)
            guard = timeout_seconds + GUARD_GRACE_SECONDS
        except ImportError as exc:  # the SDK is an optional install: pip install -r rag/requirements-llm.txt
            return template_result(evidence, "error", f"SDK not installed ({type(exc).__name__}: {_scrub(exc, key)}); "
                                   "install it with: pip install -r rag/requirements-llm.txt", **info)
        except Exception as exc:  # noqa: BLE001 - a bad setting must not break the explanation
            return template_result(evidence, "error", f"{type(exc).__name__}: {_scrub(exc, key)}", **info)

    began = time.perf_counter()
    try:
        text = _call_with_timeout(complete, prompt, guard)
    except Exception as exc:  # noqa: BLE001 - every failure of the call falls back to the template
        latency = round((time.perf_counter() - began) * 1000)
        reason = "rate limit" if _is_rate_limit(exc) else ("timeout" if _is_timeout(exc) else "error")
        detail = f"{type(exc).__name__}: {_scrub(exc, key)}"
        extra = {"http_attempts": len(attempt_log)} if attempt_log else {}
        return template_result(evidence, reason, detail, latency_ms=latency, **extra, **info)
    latency = round((time.perf_counter() - began) * 1000)
    if not isinstance(text, str) or not text.strip():
        return template_result(evidence, "error", "the model returned no text", latency_ms=latency,
                               **({"http_attempts": len(attempt_log)} if attempt_log else {}), **info)
    extra = {"http_attempts": len(attempt_log)} if attempt_log else {}
    reason, detail = check_output(text, evidence)
    if reason:
        return template_result(evidence, reason, detail, latency_ms=latency, rejected_text=text, **extra, **info)
    if cache_on:
        cache_put(directory, ckey, provider, model, text.strip())  # only text that passed all three guardrails
    return {"text": text.strip(), "source": "llm", "fallback_reason": None, "detail": "", "latency_ms": latency,
            **extra, **info}
