"""The optional LLM explanation (rag/llm_summary.py). NO test calls the network: every model is a fake function, and
the two SDKs are replaced by small fake modules. The evidence dicts are hand-made (no database)."""
import json
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from rag import llm_summary as llm
from rag.summary import summarize_evidence

KEY = "sk-test-SECRET-123"
NO_FILE = Path("does-not-exist.env")  # so the repository's own .env is never read by a test


def entry(pid, year, title=None, **extra):
    return {"paper_id": pid, "title": title or f"Title of {pid}", "year": year, "venue": "Some Venue",
            "source_sentence": None, "extractor": "ex-1", **extra}


def make_evidence():
    return {
        "pair": {"a": {"kind": "method", "id": 1, "name": "Method One"}, "b": {"kind": "task", "id": 2, "name": "Task One"}},
        "corpus": {"cutoff_year": 2024, "universe_size": 11, "n_a": 7, "n_b": 6, "observed": 2, "expected": 7 * 6 / 11},
        "yearly": [{"year": y, "a": 1, "b": 1, "both": 0} for y in (2022, 2023, 2024)],
        "roles": {
            "supports_A": [entry("W11", 2021, source_sentence="We apply method one to a new corpus.")],
            "supports_B": [entry("W12", 2020)],
            "bridge": [],
            "nearest_existing": [entry("W1", 2020, tier="exact", similarity=None, uses="both",
                                       source_sentence="We combine them."),
                                 entry("W2", 2019, tier="close", similarity=0.8123, uses="a")],
        },
        "limitations": ["Counts depend on the analyzed corpus and on extraction coverage."],
    }


GOOD = ("What the corpus shows\n"
        "Up to 2024, 11 papers in the analyzed corpus have both a method and a task. Method One is used in 7 papers and "
        "Task One in 6; together they appear in 2 papers, where about 3.82 would be expected [paper:W1]. The nearest "
        "related paper is [paper:W2], which uses Method One.\n\n"
        "What the system infers\n"
        "This pair is potentially underexplored in the analyzed corpus. The counts depend on the extraction and on the "
        "analyzed corpus, so this is a candidate for human review [paper:W11].")


def run(evidence, complete, **kwargs):
    return llm.explanation_text(evidence, use_llm=True, complete=complete, env={}, env_file=NO_FILE, **kwargs)


# --- the default is the template ---------------------------------------------------------------------------

def test_the_default_is_the_template_summary():
    ev = make_evidence()
    out = llm.explanation_text(ev, env={}, env_file=NO_FILE)
    assert out["source"] == "template" and out["fallback_reason"] is None
    assert out["text"] == summarize_evidence(ev)


def test_the_environment_variable_turns_it_on_and_the_argument_overrides_it():
    ev = make_evidence()
    on = {"PC_LLM_SUMMARY": "1"}
    assert llm.explanation_text(ev, env=on, env_file=NO_FILE)["fallback_reason"] == "no key"   # tried, had no key
    assert llm.explanation_text(ev, use_llm=False, env=on, env_file=NO_FILE)["fallback_reason"] is None
    assert llm.explanation_text(ev, use_llm=True, env={}, env_file=NO_FILE)["fallback_reason"] == "no key"
    assert llm.explanation_text(ev, env={"PC_LLM_SUMMARY": "0"}, env_file=NO_FILE)["source"] == "template"
    assert llm.explanation_text(ev, env={"PC_LLM_SUMMARY": "true"}, env_file=NO_FILE)["fallback_reason"] is None


# --- good output is accepted ----------------------------------------------------------------------------------

def test_good_output_is_accepted():
    out = run(make_evidence(), lambda prompt: GOOD)
    assert out["source"] == "llm" and out["fallback_reason"] is None
    assert out["text"] == GOOD.strip() and out["provider"] == "gemini" and out["model"] == "gemini-3.8-flash"


def test_the_word_first_inside_another_word_is_not_a_forbidden_phrase():
    out = run(make_evidence(), lambda prompt: GOOD + " The first topic is Method One.")
    assert out["source"] == "llm"


# --- guardrails reject bad output and fall back to the template ----------------------------------------------

def fell_back(out, reason):
    assert out["source"] == "template" and out["fallback_reason"] == reason, out
    assert out["text"] == summarize_evidence(make_evidence())
    return out


def test_a_wrong_paper_id_is_rejected():
    out = fell_back(run(make_evidence(), lambda p: GOOD + " See also [paper:W999]."), "citation check")
    assert "W999" in out["detail"]


def test_a_malformed_marker_is_rejected():
    fell_back(run(make_evidence(), lambda p: GOOD + " See [paper:W1 for details."), "citation check")


def test_an_invented_number_is_rejected():
    out = fell_back(run(make_evidence(), lambda p: GOOD.replace("7 papers", "9 papers")), "number check")
    assert "9" in out["detail"]


@pytest.mark.parametrize("written", ["3.82", "3.8", "3.80", "4", "4.0"])   # the evidence says 3.82
def test_a_number_and_its_roundings_are_accepted(written):
    out = run(make_evidence(), lambda p: GOOD.replace("3.82", written))
    assert out["source"] == "llm", out


@pytest.mark.parametrize("written", ["3.9", "3.7", "5", "3.83", "38.2", "13"])  # not roundings of anything in the evidence
def test_a_number_that_is_no_rounding_of_an_evidence_number_is_rejected(written):
    out = fell_back(run(make_evidence(), lambda p: GOOD.replace("3.82", written)), "number check")
    assert written in out["detail"]


def test_the_percent_form_of_a_ratio_in_the_evidence_is_accepted():
    ev = make_evidence()                       # the nearest close paper W2 has the ratio 0.8123 -> shown as 0.81
    for written in ("81", "81.0", "81%", "0.8"):
        text = GOOD + f" Its embedding similarity is {written} [paper:W2]."
        assert run(ev, lambda p, t=text: t)["source"] == "llm", written
    out = fell_back(run(ev, lambda p: GOOD + " Its similarity is 82% [paper:W2]."), "number check")
    assert "82" in out["detail"]


def test_a_count_is_not_a_ratio_so_it_has_no_percent_form():
    # 7 papers use A: "700" must not be accepted as 7 * 100
    fell_back(run(make_evidence(), lambda p: GOOD.replace("7 papers", "700 papers")), "number check")


def test_every_number_of_the_evidence_text_is_accepted_as_written():
    ev = make_evidence()
    evidence_numbers = llm.numbers_in(llm.evidence_text(ev))
    assert llm.unexplained_numbers(" ".join(sorted(evidence_numbers)), llm.evidence_text(ev)) == []


def test_a_raw_id_outside_a_marker_is_rejected():
    fell_back(run(make_evidence(), lambda p: GOOD + " Paper W3021357296 is relevant."), "number check")


@pytest.mark.parametrize("sentence", [
    "This is not a proven gap.",
    "This is not a proven research gap.",
    "It is not proof of a proven research gap.",
    "There is no proven gap in the evidence.",
    "No proven research gap is shown here.",
    "It isn't a proven gap.",
    "This is NOT a Proven Research Gap.",
    "The pair is a candidate, not a proven research gap.",
])
def test_a_negated_proven_gap_is_accepted(sentence):
    out = run(make_evidence(), lambda p: GOOD + " " + sentence)
    assert out["source"] == "llm", (sentence, out)


@pytest.mark.parametrize("sentence", [
    "This is a proven gap.",
    "A proven research gap exists.",
    "Proven gap.",
    "It is not clear, but this is a proven gap.",           # the negation is in another clause
    "It is not clear that this is a proven research gap.",  # the negation is too far before the phrase
    "This is not a proven gap, but a proven research gap exists.",  # the second use is affirmative
    "Not sure. This is a proven gap.",
])
def test_an_affirmative_proven_gap_is_rejected(sentence):
    out = fell_back(run(make_evidence(), lambda p: GOOD + " " + sentence), "forbidden phrase")
    assert "proven" in out["detail"]


def test_the_template_summary_passes_all_three_checks_on_the_test_evidence():
    ev = make_evidence()
    assert llm.check_output(summarize_evidence(ev), ev) == (None, "")


@pytest.mark.parametrize("phrase", ["No one has combined them", "this has never been tried",
                                    "the first to combine them", "definitely unexplored", "a guaranteed opportunity"])
def test_forbidden_phrases_are_rejected(phrase):
    out = fell_back(run(make_evidence(), lambda p: GOOD + f" This is {phrase}."), "forbidden phrase")
    assert out["rejected_text"].startswith("What the corpus shows")


# --- failures of the call fall back ----------------------------------------------------------------------------------

def test_a_timeout_falls_back():
    began = time.perf_counter()
    out = fell_back(run(make_evidence(), lambda p: time.sleep(1.5) or GOOD, timeout_seconds=0.1), "timeout")
    assert "TimeoutError" in out["detail"] and time.perf_counter() - began < 1.0


def test_a_missing_key_falls_back_and_names_the_variable_only():
    out = llm.explanation_text(make_evidence(), use_llm=True, env={}, env_file=NO_FILE)
    fell_back(out, "no key")
    assert "GEMINI_API_KEY" in out["detail"]
    out = llm.explanation_text(make_evidence(), use_llm=True, provider="anthropic", env={}, env_file=NO_FILE)
    assert out["fallback_reason"] == "no key" and "ANTHROPIC_API_KEY" in out["detail"]


class RateLimitError(Exception):  # the name of the anthropic SDK's class
    pass


class CodedError(Exception):  # the shape of google.genai.errors.APIError: a .code attribute
    code = 429


@pytest.mark.parametrize("error", [RateLimitError("slow down"), CodedError("quota exceeded")])
def test_a_rate_limit_error_falls_back(error):
    def complete(prompt):
        raise error

    fell_back(run(make_evidence(), complete), "rate limit")


def test_any_other_error_falls_back():
    def complete(prompt):
        raise ConnectionError("no network")

    out = fell_back(run(make_evidence(), complete), "error")
    assert "ConnectionError" in out["detail"]


def test_an_empty_answer_falls_back():
    fell_back(run(make_evidence(), lambda p: "   "), "error")
    fell_back(run(make_evidence(), lambda p: None), "error")


def test_the_key_is_scrubbed_from_error_details_and_never_in_a_result(monkeypatch):
    def broken(prompt):
        raise RuntimeError(f"request failed for key {KEY}")

    monkeypatch.setattr(llm, "make_client", lambda provider, key, model, temperature=None, timeout=20, attempt_log=None: broken)
    out = llm.explanation_text(make_evidence(), use_llm=True, env={"GEMINI_API_KEY": KEY}, env_file=NO_FILE)
    assert out["fallback_reason"] == "error" and "***" in out["detail"]
    assert KEY not in json.dumps(out)


# --- the prompt contains only the evidence ------------------------------------------------------------------------

def test_the_prompt_has_the_rules_and_only_the_evidence():
    prompt = llm.build_prompt(make_evidence())
    for needed in ("What the corpus shows", "What the system infers", "potentially underexplored in the analyzed corpus",
                   "proven gap", "[paper:W11]", "Title of W11", "2021", "We apply method one to a new corpus.",
                   "3.82", "11", "Method One", "Task One", "embedding similarity 0.81"):
        assert needed in prompt, needed
    for not_sent in ("Some Venue", "ex-1"):  # fields of the evidence that are not part of the prompt
        assert not_sent not in prompt


def test_text_from_the_corpus_cannot_forge_a_marker_in_the_prompt():
    ev = make_evidence()
    ev["roles"]["supports_A"][0]["title"] = "Evil [paper:W999] title"
    assert "[paper:W999]" not in llm.build_prompt(ev)


# --- settings: the .env file, provider, model, temperature --------------------------------------------------------

def test_settings_come_from_the_environment_then_the_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nGEMINI_API_KEY=\"from-file\"\nPC_LLM_MODEL=model-from-file\n", encoding="utf-8")
    assert llm.setting("GEMINI_API_KEY", env={}, env_file=env_file) == "from-file"
    assert llm.setting("GEMINI_API_KEY", env={"GEMINI_API_KEY": "from-env"}, env_file=env_file) == "from-env"
    assert llm.setting("PC_LLM_MODEL", env={}, env_file=env_file) == "model-from-file"
    assert llm.setting("MISSING", env={}, env_file=env_file) is None
    assert llm.setting("GEMINI_API_KEY", env={"GEMINI_API_KEY": ""}, env_file=tmp_path / "none.env") is None


def test_the_repository_env_file_is_ignored_by_git():
    try:
        done = subprocess.run(["git", "check-ignore", "-q", str(llm.ENV_FILE)], cwd=llm.REPO_ROOT)
    except FileNotFoundError:
        pytest.skip("git is not available")
    assert done.returncode == 0, ".env must be ignored by git"


class ReadTimeout(Exception):  # the name of the exception httpx raises when the SDK's timeout is reached
    pass


class ServerError(Exception):  # the shape of google.genai.errors.ServerError
    code = 503


class APITimeoutError(Exception):  # the name of the anthropic SDK's timeout exception
    pass


class InternalServerError(Exception):  # the shape of anthropic.InternalServerError
    status_code = 503


def fake_sdks(monkeypatch, calls, behaviour="ok", server_seconds=3.0):
    """Fake google-genai and anthropic modules. They record how they were called and imitate the two SDK features that
    matter here: the request timeout (a call longer than the timeout it was given is cancelled: calls["cancelled"]) and
    automatic retries (calls["attempts"] counts the HTTP attempts: 1 + retries). behaviour: "ok", "slow" (the server needs
    server_seconds) or "503" (every attempt answers 503)."""
    calls.update(attempts=0, cancelled=False)
    google, genai, genai_types = types.ModuleType("google"), types.ModuleType("google.genai"), types.ModuleType("google.genai.types")

    class Options:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class GenerateContentConfig(Options):
        pass

    def one_attempt(timeout_seconds, timeout_error, server_error):
        calls["attempts"] += 1
        if behaviour == "slow":
            threading.Event().wait(min(server_seconds, timeout_seconds))
            if server_seconds > timeout_seconds:
                calls["cancelled"] = True  # the SDK gives up and closes the connection
                raise timeout_error("timed out")
        if behaviour == "503":
            raise server_error("503 UNAVAILABLE")

    class Models:
        def __init__(self, http_options):
            self.http_options = http_options

        def generate_content(self, model, contents, config):
            calls["gemini"] = {"model": model, "contents": contents, "config": config.kwargs}
            options = self.http_options.kwargs
            retry = options.get("retry_options")
            attempts = retry.kwargs.get("attempts", 5) if retry else 5   # the SDK's documented default is 5
            for _ in range(max(1, attempts)):
                try:
                    one_attempt(options["timeout"] / 1000, ReadTimeout, ServerError)
                    return types.SimpleNamespace(text=GOOD)
                except ServerError:
                    pass
            raise ServerError("503 UNAVAILABLE")

    class GeminiClient:
        def __init__(self, api_key, http_options=None):
            calls["gemini_key"], calls["gemini_http_options"] = api_key, http_options
            self.models = Models(http_options)

    genai.Client, genai_types.GenerateContentConfig, genai.types, google.genai = GeminiClient, GenerateContentConfig, genai_types, genai
    genai_types.HttpOptions, genai_types.HttpRetryOptions = Options, Options

    anthropic = types.ModuleType("anthropic")

    class Messages:
        def __init__(self, client_kwargs):
            self.client_kwargs = client_kwargs

        def create(self, **kwargs):
            calls["anthropic"] = kwargs
            retries = self.client_kwargs.get("max_retries", 2)   # the SDK's documented default is 2
            for _ in range(1 + retries):
                try:
                    one_attempt(self.client_kwargs["timeout"], APITimeoutError, InternalServerError)
                    return types.SimpleNamespace(content=[types.SimpleNamespace(type="thinking", thinking="hmm"),
                                                          types.SimpleNamespace(type="text", text=GOOD)])
                except InternalServerError:
                    pass
            raise InternalServerError("503")

    class Anthropic:
        def __init__(self, **kwargs):
            calls["anthropic_client"] = kwargs
            self.messages = Messages(kwargs)

    anthropic.Anthropic = Anthropic
    for name, module in (("google", google), ("google.genai", genai), ("google.genai.types", genai_types), ("anthropic", anthropic)):
        monkeypatch.setitem(sys.modules, name, module)


def test_the_gemini_provider_uses_the_documented_default_and_no_temperature(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls)
    out = llm.explanation_text(make_evidence(), use_llm=True, env={"GEMINI_API_KEY": KEY}, env_file=NO_FILE)
    assert out["source"] == "llm" and out["provider"] == "gemini"
    assert calls["gemini_key"] == KEY and calls["gemini"]["model"] == "gemini-3.8-flash"
    assert calls["gemini"]["config"] == {"max_output_tokens": 600}          # no temperature: ignored by this model
    options = calls["gemini_http_options"].kwargs
    assert options["timeout"] == 20000                                       # milliseconds (SDK field description)
    assert options["retry_options"].kwargs == {"attempts": 1}                # "If 0 or 1, it means no retries"
    assert "What the corpus shows" in calls["gemini"]["contents"] and KEY not in calls["gemini"]["contents"]
    assert KEY not in json.dumps(out)


def test_the_anthropic_provider_uses_the_documented_default_and_no_retries(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls)
    env = {"PC_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": KEY}
    out = llm.explanation_text(make_evidence(), use_llm=True, env=env, env_file=NO_FILE)
    assert out["source"] == "llm" and out["provider"] == "anthropic" and out["text"] == GOOD.strip()
    assert calls["anthropic_client"] == {"api_key": KEY, "timeout": 20.0, "max_retries": 0}
    sent = calls["anthropic"]
    assert sent["model"] == "claude-haiku-5-5" and sent["max_tokens"] == 600 and "temperature" not in sent
    assert sent["messages"][0]["role"] == "user" and "EVIDENCE" in sent["messages"][0]["content"]
    assert KEY not in json.dumps(out)


def test_model_and_temperature_settings_are_passed_on_only_when_set(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls)
    env = {"GEMINI_API_KEY": KEY, "PC_LLM_MODEL": "my-model", "PC_LLM_TEMPERATURE": "0"}
    llm.explanation_text(make_evidence(), use_llm=True, env=env, env_file=NO_FILE)
    assert calls["gemini"]["model"] == "my-model" and calls["gemini"]["config"] == {"max_output_tokens": 600, "temperature": 0.0}


def test_an_unknown_provider_falls_back():
    out = llm.explanation_text(make_evidence(), use_llm=True, provider="nope", env={}, env_file=NO_FILE)
    assert out["fallback_reason"] == "error" and "unknown provider" in out["detail"]


def test_a_missing_sdk_falls_back(monkeypatch):
    monkeypatch.setitem(sys.modules, "google", None)  # makes `from google import genai` raise ImportError
    out = llm.explanation_text(make_evidence(), use_llm=True, env={"GEMINI_API_KEY": KEY}, env_file=NO_FILE)
    assert out["fallback_reason"] == "error" and "SDK not installed" in out["detail"] and "requirements-llm.txt" in out["detail"] and KEY not in json.dumps(out)


def test_no_test_needs_the_network():
    # the module imports no SDK at import time
    assert "google" not in llm.__dict__ and "anthropic" not in llm.__dict__


# --- real timeouts and no hidden retries ----------------------------------------------------------------------

def gemini_env():
    return {"GEMINI_API_KEY": KEY}


def test_a_call_longer_than_the_timeout_is_cancelled_by_the_sdk_and_falls_back_as_timeout(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls, behaviour="slow", server_seconds=3.0)
    began = time.perf_counter()
    out = llm.explanation_text(make_evidence(), use_llm=True, env=gemini_env(), env_file=NO_FILE, timeout_seconds=0.2)
    assert calls["gemini_http_options"].kwargs["timeout"] == 200             # our timeout went to the SDK, in ms
    assert calls["cancelled"] is True and calls["attempts"] == 1             # the SDK cancelled it, once
    assert out["fallback_reason"] == "timeout" and out["source"] == "template" and "ReadTimeout" in out["detail"]
    assert time.perf_counter() - began < 1.5, "the SDK's timeout fired long before the outer guard (timeout + 5 s)"


def test_the_anthropic_call_is_cancelled_by_the_sdk_too(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls, behaviour="slow", server_seconds=3.0)
    env = {"PC_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": KEY}
    out = llm.explanation_text(make_evidence(), use_llm=True, env=env, env_file=NO_FILE, timeout_seconds=0.2)
    assert calls["anthropic_client"] == {"api_key": KEY, "timeout": 0.2, "max_retries": 0}
    assert calls["cancelled"] is True and calls["attempts"] == 1
    assert out["fallback_reason"] == "timeout" and "APITimeoutError" in out["detail"]


def test_after_a_503_the_gemini_sdk_is_not_asked_to_retry(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls, behaviour="503")
    out = llm.explanation_text(make_evidence(), use_llm=True, env=gemini_env(), env_file=NO_FILE)
    assert calls["attempts"] == 1, "exactly one HTTP attempt"
    assert out["fallback_reason"] == "error" and "ServerError" in out["detail"] and "503" in out["detail"]


def test_after_a_503_the_anthropic_sdk_is_not_asked_to_retry(monkeypatch):
    calls = {}
    fake_sdks(monkeypatch, calls, behaviour="503")
    env = {"PC_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": KEY}
    out = llm.explanation_text(make_evidence(), use_llm=True, env=env, env_file=NO_FILE)
    assert calls["attempts"] == 1 and out["fallback_reason"] == "error" and "InternalServerError" in out["detail"]


def test_the_fake_really_retries_when_not_told_not_to(monkeypatch):
    """Guards the tests above: with the SDK's documented defaults the fake makes 5 (gemini) or 3 (anthropic) attempts."""
    calls = {}
    fake_sdks(monkeypatch, calls, behaviour="503")
    fake_types = sys.modules["google.genai.types"]
    from google import genai
    client = genai.Client(api_key=KEY, http_options=fake_types.HttpOptions(timeout=1000))
    with pytest.raises(ServerError):
        client.models.generate_content(model="m", contents="c", config=fake_types.GenerateContentConfig())
    assert calls["attempts"] == 5
    calls["attempts"] = 0
    import anthropic
    with pytest.raises(InternalServerError):
        anthropic.Anthropic(api_key=KEY, timeout=5.0).messages.create(model="m", max_tokens=1, messages=[])
    assert calls["attempts"] == 3


def test_the_outer_guard_is_a_daemon_thread_so_the_process_can_exit():
    release = threading.Event()
    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        llm._call_with_timeout(lambda prompt: release.wait(30), "x", 0.1)
    assert time.perf_counter() - started < 1.0
    stuck = [t for t in threading.enumerate() if t.name == "llm-call"]
    assert stuck and all(t.daemon for t in stuck), "a stuck call must not be able to keep the interpreter alive"
    release.set()
    for t in stuck:
        t.join(2)
    assert not [t for t in threading.enumerate() if t.name == "llm-call"], "the thread ends once the call ends"


def test_timeout_exceptions_of_the_sdks_are_recognised():
    assert llm._is_timeout(ReadTimeout("x")) and llm._is_timeout(APITimeoutError("x")) and llm._is_timeout(TimeoutError())
    assert not llm._is_timeout(ServerError("x")) and not llm._is_timeout(ValueError("x"))


# --- the REAL google-genai SDK against a local server (skipped when the SDK is not installed) ---------------------

@pytest.fixture
def local_server():
    import http.server

    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        mode = "503"

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            hits.append(self.path)
            if Handler.mode == "slow":
                time.sleep(3)
            body = json.dumps({"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}).encode()
            try:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Handler, hits, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_the_real_gemini_sdk_times_out_and_makes_exactly_one_request(local_server):
    pytest.importorskip("google.genai")
    handler, hits, base = local_server
    handler.mode = "slow"
    attempts = []
    complete = llm.gemini_client("fake-key", "gemini-3.8-flash", timeout=0.5, attempt_log=attempts, base_url=base)
    began = time.perf_counter()
    with pytest.raises(Exception) as caught:
        complete("hello")
    assert llm._is_timeout(caught.value), type(caught.value).__mro__
    assert time.perf_counter() - began < 2.0, "cancelled at the timeout, not after the server's 3 s"
    assert len(attempts) == 1 and len(hits) == 1, (len(attempts), len(hits))


def test_the_real_gemini_sdk_makes_exactly_one_request_after_a_503(local_server):
    pytest.importorskip("google.genai")
    handler, hits, base = local_server
    handler.mode = "503"
    attempts = []
    complete = llm.gemini_client("fake-key", "gemini-3.8-flash", timeout=5, attempt_log=attempts, base_url=base)
    with pytest.raises(Exception) as caught:
        complete("hello")
    assert type(caught.value).__name__ == "ServerError" and getattr(caught.value, "code", None) == 503
    assert len(attempts) == 1 and len(hits) == 1, "the request hook and the server agree: one attempt, no retry"
