# Optional LLM explanation (rag/llm_summary.py)

The explanation of an opportunity is the fixed-template summary of `rag/summary.py` by default. This module adds an
**optional** LLM version. It is **off by default**, it never replaces the template without passing three checks, and
any problem returns the template with a stated reason. Candidate opportunities stay signals for human review ("potentially
underexplored in the analyzed corpus"), not proof of a gap.

Status (2026-11-21): the code and its 60 tests (fake clients, no network) are done, and the API tests that touch the new
fields ran and passed (see below). **A real check was run once with Gemini and produced no model text at all: all 3 calls fell
back to the template** (one timeout, two 503 "high demand" errors; details in "Real check" below). So the number and phrase
guardrails have **not yet been tested on a real model answer**. The SDK calls follow the SDKs' documented examples; the Gemini
one has now been exercised against the real service (it reached it and got errors), the Anthropic one only against fake
modules.

API tests: run in a separate environment (`pc-envs/api-venv`, Python 3.12.3, the pins of `requirements-person3.txt`):
`pytest api` gave 19 passed and 7 skipped (the PostgreSQL integration tests, which need `PC_TEST_PG_DSN`); with
`PC_TEST_PG_DSN` pointing at a throwaway database, `pytest api scoring` gave 62 passed, including the `explain` integration
test that goes through `PostgresRepository.explain`.

## What is sent to the API

Only the evidence object that the template summary uses, written as text (`evidence_text()`), plus the fixed rules
(`RULES`). The fields:

- the pair: kind and name of A and of B;
- the corpus counts: cutoff year, papers in the analyzed corpus, papers using A, papers using B, papers using both
  together (observed), the expected count (two decimals);
- papers per year for the last 3 years in the data (using A, using B, using both);
- for each role (papers that use A but not B, papers that use B but not A, bridge papers, nearest existing work): the
  `[paper:ID]` marker, the title and the year; for nearest existing work also the match tier, the embedding similarity
  and which element the paper uses; for the supporting and nearest papers the stored source sentence;
- the limitations list.

Not sent: venues, extractor names, abstracts, author data, database names, the API key, anything else. Text from the corpus
(titles, source sentences) is cleaned so it cannot forge a `[paper:...]` marker. Note that this corpus text is written by
third parties and goes into the prompt as it is; the checks below limit what a manipulated answer could do, but they are not
a defence against prompt injection.

A typical prompt is about 5,600 to 5,900 characters (about 800 to 860 words) for the three demo pairs on `pc_pilot`
(measured with `build_prompt` on the real evidence, read only). The output limit is about 600 tokens, the timeout 20 seconds,
and there are no retries.

## What is checked (the same for both providers)

After the model answers, in this order:

1. **Citations**: `rag.citations.verify_citations` must pass: every `[paper:ID]` is an id from the evidence and no marker is
   malformed. Reason on failure: `citation check`.
2. **Numbers**: every number in the answer (ignoring the ids inside markers) must equal a number in the evidence text sent
   to the model, or a rounding of one to 0, 1 or 2 decimals (half up or half to even: 3.82 may be written 3.82, 3.8 or 4), or,
   for a ratio in the evidence (a number from 0 to 1 written with decimals, such as the embedding similarity 0.81), its
   percent form (81, 81.0, 81%). Anything else is rejected: an invented count, a wrong rounding (3.9), a paper id written
   outside a marker, or a percent of a plain count. Reason on failure: `number check`. The template summary passes this check
   on the three demo pairs (it rounds the expected count to one decimal, which is allowed). The check compares numbers as
   text; it does not understand units, ranges or number words ("two"). Rounding is also a way in for a wrong claim: "about 4"
   is accepted for 3.82 although it is a different statement, and a number that is a rounding of an unrelated evidence number
   (for example a year) would pass.
3. **Forbidden phrases** (case-insensitive): "no one has", "never been", "first to" (whole words), and from AGENTS.md
   "definitely unexplored", "guaranteed", "nobody has done" are always rejected. "proven gap" and "proven research gap" are
   rejected unless one of the 4 words before them, in the same clause (no comma, full stop, semicolon, colon, question or
   exclamation mark between), is a negation (not, no, isn't, aren't, wasn't, weren't): "is not a proven research gap", "not
   proof of a proven gap" and "no proven gap" pass; "this is a proven gap", "a proven research gap exists" and "it is not
   clear that this is a proven gap" (negation too far away) are rejected. Reason on failure: `forbidden phrase`.

## Fallback

`explanation_text(evidence)` returns `{text, source, fallback_reason, detail, ...}`.

| Situation | source | fallback_reason |
| --- | --- | --- |
| Option off (the default) | template | null |
| On, but no key | template | `no key` |
| Network error, API error, timeout (20 s), empty answer, SDK not installed, unknown provider | template | `error` (the exception type and a short message in `detail`) |
| HTTP 429 / `RateLimitError` | template | `rate limit` |
| Failed citation / number / phrase check | template | `citation check` / `number check` / `forbidden phrase` |
| Passed everything | llm | null |

`detail` and the extra keys (`provider`, `model`, `latency_ms`, `rejected_text`) are for debugging; the API response only
adds `summary_source` and `summary_fallback_reason` to `POST /opportunities/{id}/explain`. The key never appears in a result
or in a message (it is scrubbed from error text). `citation_check` in the API response is computed on whichever text is
returned.

## How to turn it on

1. Install the SDKs (they are optional and not installed yet; the pins are the current PyPI releases on 2026-11-21):
   `pip install -r rag/requirements-llm.txt` in the environment that runs the API.
2. Put the key in the file **`.env` at the repository root** (`paper-compass-main\.env`, next to `README.md`). It is ignored by
   git (checked with `git check-ignore`: rule `.gitignore:1:.env`). One line per setting, no spaces around `=`:

   ```
   GEMINI_API_KEY=your-key-here
   PC_LLM_SUMMARY=1
   ```

   (or `ANTHROPIC_API_KEY=...` with `PC_LLM_PROVIDER=anthropic`). Environment variables override the file. Never paste a key
   into a chat, a commit, an issue or a log.
3. Restart the API. `PC_LLM_SUMMARY=1` turns it on; without it the template is used. In code,
   `explanation_text(evidence, use_llm=True)` or `repository.explain(id, use_llm=True)` overrides the variable.

## Providers

| | gemini (default) | anthropic |
| --- | --- | --- |
| Select with | `PC_LLM_PROVIDER=gemini` (or leave unset) | `PC_LLM_PROVIDER=anthropic` |
| Key variable | `GEMINI_API_KEY` | `ANTHROPIC_API_KEY` |
| SDK | `google-genai` | `anthropic` |
| Default model | `gemini-3.8-flash` | `claude-haiku-5-5` |
| Where the default was checked | https://aistudio.google.com/docs/models/gemini-3.8-flash (ai.google.dev redirects there): "Model code gemini-3.8-flash", "Stable: gemini-3.8-flash", no deprecation date | https://platform.claude.com/docs/en/models/haiku-5-5/overview: "Model ID: claude-haiku-5-5", "Active (latest)", retirement not sooner than October 7, 2027 |
| Override the model | `PC_LLM_MODEL=...` | `PC_LLM_MODEL=...` |
| Temperature | not sent (the Gemini docs say 3.6+ models ignore a custom value) | not sent (the Haiku 5.5 page says to omit it) |
| Timeout | 20 s, enforced around the call (the SDK's own timeout units were not found in the docs) | 20 s in the SDK client, and enforced around the call; `max_retries=0` |

Both pages were read on 2026-11-21 by a fetch of the page text; the Gemini model page gives no statement about
temperature or about rate limits.

`PC_LLM_TEMPERATURE=0` makes the code send a temperature (for a model that accepts it). **The requested temperature of 0 is
therefore not applied with either default model**: output can vary between runs, which is one more reason the answer is
checked after generation.

## Before the demo

- **Free-tier terms and limits must be checked by the team** (rate limits, whether prompts may be used for training, data
  location, cost). This was not checked here. The pages above state prices for Claude Haiku 5.5, and the Gemini model page links
  to a pricing page; neither was evaluated.
- Check that the model names above still exist on the day.
- Run one real call per provider you plan to use. Gemini 3.8 Flash supports "thinking" (levels low, medium, high; it cannot be
  switched off). Whether thinking tokens count against the 600-token output limit was not checked; if they do, an answer can
  come back empty or cut off, which falls back to the template (`error`: "the model returned no text", or a failed check).

## Limitations

- The guardrails check ids, numbers and phrases. They **cannot verify that every sentence is faithful to the evidence**: a
  sentence can use only allowed ids and numbers and still say something the evidence does not support. A human reviewer
  remains necessary, and the template summary is the only text whose every sentence is fixed by code.
- The structure (two paragraphs, the two titles) is requested in the prompt but not enforced.
- The number check compares tokens as text; it does not understand units, ranges or number words ("two").
- The guardrails have not been exercised on a real model answer yet (the first real check returned none, see "Real check").

## Real check (2026-11-21, once)

Setup: provider **gemini** (`PC_LLM_PROVIDER` not set, so the default), model **gemini-3.8-flash** (the default), `PC_LLM_SUMMARY=1`,
key in the gitignored root `.env` (copied into the worktree for the run; not printed or logged), SDK `google-genai==3.6.1`
installed in a separate environment (`pc-envs/api-venv`). Evidence built read-only from `pc_pilot` (cutoff 2026, 3 papers per
role). One call per demo pair, no retries by the code, 3 calls in total:

| Pair | Latency | source | fallback_reason | What happened |
| --- | ---: | --- | --- | --- |
| Masked Language Modeling x Machine Translation | 20,031 ms | template | error | `TimeoutError: no answer within 20 s` (our 20 s limit) |
| Data Augmentation x Language Modeling | 7,571 ms | template | error | `ServerError: 503 UNAVAILABLE` ... "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later." |
| Recurrent Neural Network x Machine Translation | 2,371 ms | template | error | the same 503 UNAVAILABLE message |

Result: **0 of 3 answers passed the guardrails, because none was returned**; all 3 explanations were the template summary.
The guardrails (citations, numbers, phrases) therefore have no real output to show yet. None of the errors is a rate-limit or
quota error (a 429); they are a timeout and "service unavailable / high demand" responses from the model, which may be
temporary.

What I could not tell:
- Whether the first call was slow because the service was overloaded: it ran past our 20 s limit, and the abandoned call kept
  the Python process alive for more than 4 more minutes until I stopped it. The SDK may have retried that request on its own
  in the background (the SDK's retry behaviour was not set or checked), so the number of HTTP requests actually sent to the
  service for call 1 is unknown; the code itself made exactly 3 calls.
- Whether the 600-token output limit and the model's thinking would have allowed a complete answer; no answer arrived.

Follow-ups before relying on this (not done): rerun when the service is less busy (or try another model by `PC_LLM_MODEL`
after checking the docs); check the SDK's own timeout and retry settings in the official docs and set them, so a timed-out
call is really cancelled and does not keep running; run a real call for the other provider if it will be used.
