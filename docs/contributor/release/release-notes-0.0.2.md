(AI generated. Not reviewed.)

# Fichero 0.0.2 Release Notes

> Backend Merge + Bug Fixes — the stability + reliability release before
> Search v1 (0.0.3) lands.

---

## What's new for users

### Catalogue narrative is finally reliable across languages

If you've imported documents in **Spanish, French, Italian, German, or
any non-English language**, the catalogue workflow now completes
end-to-end. Previously, Apple Intelligence's on-device model would
silently reject prompts in unsupported locales and leave the catalogue
empty. Fichero now detects the rejection, automatically routes the
request to your configured cloud model (the `$large` slot in
Settings → AI Defaults), and finishes the run.

The same fallback covers Apple's safety-filter refusals on academic
content (court records, ethnographic literature, scholarly text) — your
folder gets catalogued from the cloud instead of getting stuck.

### Catalogue entries are sharper

The narrative paragraph the catalogue tool writes now uses
**reasoning-enabled generation** when your `$large` slot points at a
model that supports it (Claude Sonnet 4.6, GPT-5/o-series). The model
spends a few extra seconds planning the structure and picking salient
entities before writing — the result is grounded in concrete names,
dates, and places instead of stock framing like "This document is…".

Cost: roughly two cents extra per catalogue run. Latency: 5-15 seconds
extra. Off by default everywhere except this one synthesis call.

### Per-section claim caps are tunable

The catalogue narrative gets fed a context block listing the entities
the extractors found. On dense folders (100+ contributors in
acknowledgments, ledgers, etc.) the prompt would balloon and OpenRouter
would time out. Each section (people, places, organizations, events,
dates, keywords) is now capped — defaults of 30/20/15/15/30/30 work for
most folders, and you can override per-workflow if you have unusual
shapes. See the catalogue node's **Advanced** config section.

---

## What's new under the hood

### Reliability wins

- **Centralized timeout formulas.** All LLM calls now share one
  `_compute_timeout(config, kind)` helper instead of three separate
  formulas. Wall-clock budgets scale with `max_tokens` (a 4K-token
  narrative gets more budget than a 200-token tag list) and, for
  Apple structured calls, schema complexity.
- **Async-safe locale precheck.** `apple_intelligence_supports_locale`
  no longer blocks the event loop on its 50ms subprocess probe.
- **Schema converter fails loud.** Pydantic shapes that Apple's
  `DynamicGenerationSchema` can't model (discriminated unions, enums,
  recursive types, format keywords) now raise a clear field-pointing
  error at conversion time instead of producing a partial tree that
  fm-bridge later rejects with an opaque message.
- **fm-bridge build is clean.** Renamed `main.swift` → `FmBridge.swift`
  to silence SourceKit's `@main` warning.

### Cost tracking foundation

Every LLM call now emits a structured usage log with
`input_tokens`/`output_tokens`/`total_tokens`. Apple Intelligence
entries are marked `(estimated)` — the Foundation Models API doesn't
expose token counts to the bridge yet, so we estimate from character
counts (~10% accurate). Cloud entries carry provider-reported counts
exactly.

A new `collect_usage()` context manager lets workflow runners (and any
other consumer) capture every LLM call's usage during a code block:

```python
from fichero.llm import collect_usage

with collect_usage() as bucket:
    result = await tool_fn(inputs)
# bucket = list of usage dicts ready for the activity store
```

The runner integration that writes the bucket into Activity metadata
ships in 0.0.3.

### Integration tests for the LLM fallback chain

10 new integration tests in `tests/integration/test_llm_fallback_chain.py`
cover the most critical reliability path end-to-end with mocks at the
network boundary (no internet calls). They lock in the contract that
Apple-unavailable errors route to `$large` while transient errors
propagate for chunked retry.

### Documentation

The backend development standards doc now has six
documented contracts under "LLM Stack Architecture (post-#872)" covering
the error hierarchy, timeout helper, reasoning routing, schema fail-loud
guarantee, fm-bridge canonical decision, and the `collect_usage`
primitive. New contributors should read this before touching `llm.py`.

---

## Stats

- **22 issues closed** across two overnight sessions on the #872
  master plan
- **440+ unit tests passing**, 0 regressions, ruff clean
- 0.0.2 milestone: **96% complete** — only the release packaging chain
  (notarization, signing, content writing) remains, and that's
  Daniel-blocked

---

## Deferred to 0.0.3

- **#868** LLMProvider Protocol refactor — architectural shape, no
  behavior change. Foundation laid (centralized timeouts, typed error
  hierarchy, reasoning routing, usage collector); the actual
  AppleProvider/LangChainNativeProvider/OpenRouterProvider/OpenAICompatProvider
  subclass work runs in 0.0.3.
- **#873** pytest integration test — pieces 2 (workflow-execution
  runner with mocked tools) and 3 (FastAPI route E2E) need
  fixture-infra design.
- **#821** Apple Intelligence Tool protocol (model calling back into
  the KG) — feature work, not behavior fix.
- **#854** Apple SDK 26.4 proactive token budgeting — external blocker
  on macOS SDK release.

---

## Looking ahead — Search v1 (0.0.3)

The next release wires the search input end-to-end: type a query → results
list appears within 2 seconds → click a result → document opens in the
inspector. The backend is already in place; only the SwiftUI input
surface needs the `.searchable(text:)` modifier and submit-handling. See
release gate **#481**.
