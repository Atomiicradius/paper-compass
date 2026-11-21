# Optional LLM explanation (rag/llm_summary.py)

The explanation of an opportunity is the fixed-template summary of `rag/summary.py` by default. This module adds an
**optional** LLM version. It is **off by default**, it never replaces the template without passing three checks, and
any problem returns the template with a stated reason. Candidate opportunities stay signals for human review ("potentially
underexplored in the analyzed corpus"), not proof of a gap.

Status when this was written (2026-11-21): the code and its 32 tests (fake clients, no network) are done. **The real
providers have not been called**: no API key was set on the machine, and the two SDKs are not installed, so the real
check (Part 3 of the task) was skipped with 0 API calls. The SDK calls in `gemini_client` and `anthropic_client` follow
the SDKs' documented examples but have only been exercised against fake modules.

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
2. **Numbers**: every number in the answer (ignoring the ids inside markers) must appear, written the same way, in the
   evidence text sent to the model. So "3.8" is rejected when the evidence says "3.82", and a paper id written outside a
   marker is rejected. Reason on failure: `number check`. This is strict on purpose. For the three demo pairs, the
   template summary itself fails this check because it rounds the expected count to one decimal (for example 4.0 where the
   evidence says 4.04); a model that rounds will fall back too. The prompt tells the model to copy numbers exactly.
3. **Forbidden phrases** (case-insensitive): "proven gap", "no one has", "never been", "first to" (whole words), and from
   AGENTS.md "definitely unexplored", "guaranteed", "nobody has done". The check does not look at negation, so "not a proven
   gap" is rejected too. Reason on failure: `forbidden phrase`.

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
- The API tests for the new response fields (`api/tests/test_api.py`) were written but not run, because `fastapi` is not
  installed in the available environments; the mock repository path was run directly.
