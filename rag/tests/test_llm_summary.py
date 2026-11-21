"""The optional LLM explanation (rag/llm_summary.py). NO test calls the network: every model is a fake function, and
the two SDKs are replaced by small fake modules. The evidence dicts are hand-made (no database)."""
import json
import subprocess
import sys
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


@pytest.mark.parametrize("phrase", ["a proven gap", "No one has combined them", "this has never been tried",
                                    "the first to combine them", "definitely unexplored", "a guaranteed opportunity"])
def test_forbidden_phrases_are_rejected(phrase):
    out = fell_back(run(make_evidence(), lambda p: GOOD + f" This is {phrase}."), "forbidden phrase")
    assert out["rejected_text"].startswith("What the corpus shows")


# --- failures of the call fall back ----------------------------------------------------------------------------------

def test_a_timeout_falls_back():
    began = time.perf_counter()
    out = fell_back(run(make_evidence(), lambda p: time.sleep(1.5) or GOOD, timeout_seconds=0.1), "error")
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

    monkeypatch.setattr(llm, "make_client", lambda provider, key, model, temperature=None: broken)
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


def fake_sdks(monkeypatch, calls):
    """Fake google-genai and anthropic modules that record how they were called."""
    google, genai, genai_types = types.ModuleType("google"), types.ModuleType("google.genai"), types.ModuleType("google.genai.types")

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Models:
        def generate_content(self, model, contents, config):
            calls["gemini"] = {"model": model, "contents": contents, "config": config.kwargs}
            return types.SimpleNamespace(text=GOOD)

    class GeminiClient:
        def __init__(self, api_key):
            calls["gemini_key"] = api_key
            self.models = Models()

    genai.Client, genai_types.GenerateContentConfig, genai.types, google.genai = GeminiClient, GenerateContentConfig, genai_types, genai

    anthropic = types.ModuleType("anthropic")

    class Messages:
        def create(self, **kwargs):
            calls["anthropic"] = kwargs
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="thinking", thinking="hmm"),
                                                  types.SimpleNamespace(type="text", text=GOOD)])

    class Anthropic:
        def __init__(self, **kwargs):
            calls["anthropic_client"] = kwargs
            self.messages = Messages()

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
