# Workflow Exercise Report — 2026-09-02/03 (overnight)

Systematic end-to-end exercise of the shipped workflow presets through the
CLI/HTTP API, on a real (scratch) library, across four model configurations.
Every run went through `scripts/exercise_workflows.py` (new; sibling of
`exercise_tools.py` — that one proves TOOLS in-process, this one proves
PRESETS the way a user runs them). Raw per-run JSON lives in
`agent-work/design/workflow-exercise/`.

## Setup

- **Engine**: this worktree's code, isolated on `https://127.0.0.1:8767`
  (own `FICHERO_BASE_PATH` + `FICHERO_TOKEN_DIR`, beta feature tier so
  `/api/workflows` is served). No real library under `~/Fichero` was touched.
- **Sample**: 7 pages copied from the Marshall 1923 diary source images into
  a fresh `Scratch.fichero` (cover, calendar page, and five diary pages —
  typescript-adjacent handwriting, tables, dates).
- **Screen was LOCKED the whole night** (`CGSSessionScreenIsLocked: true`).
  Apple Vision OCR baseline was verified sane before anything else: the
  cover page transcribed to the expected "The Diary of N.C. Marshall / 1923"
  and the diary pages match the reference transcripts. **Apple Vision OCR is
  not degraded by the locked session.**
- 51 presets seeded; 126 tools registered.

## Matrix — workflow × model

Legend: ✓ ran end-to-end and persisted its artifact · ✗→✓ failed, root
cause fixed and committed tonight, re-verified green · ⊘ correct,
well-worded refusal (model capability), not a defect · ✗ environment limit.

| Workflow | apple (vision+small) | omlx Qwen3-VL-8B local | ollama qwen3.5:cloud | openrouter gemini-3.1-flash-lite |
|---|---|---|---|---|
| Transcribe | ✗→✓ (cache-hit bug) | — | — | — |
| Transcribe (Auto-Detect) | ⊘ classify needs generative vision | — | — | ✓ 11.6s |
| Clean Up Text (programmatic) | ✗→✓ (missing documents edge; silent no-save) | n/a | — | — |
| Clean Up Text (LLM mode) | — | ✓ (via exercise workflow) | ✗ quota | — |
| Translate | ✗→✓ (missing documents edge) 42.7s | ✓ 52.7s | ✗ quota | — |
| Diary Entries | ✓ 68.3s | ✓ 37.2s | ✗ quota | — |
| NER per-page (local) | ✓ 448s | ✓ 17.5s | — | — |
| Catalogue (12 nodes) | ✓ 154s | — | — | — |
| Detect Regions (Apple Vision) | ✓ 15.3s | — | — | — |
| Detect Regions (VLM) | ⊘ needs generative vision | ⊘ mlx_lm is text-only | — | ✓ (after setting the $vision_medium tier) |
| Describe (visual) | ⊘ | ⊘ mlx_lm is text-only | — | ✓ |
| Extract Table | ⊘ (preflight 400) | — | — | ✓ 5.7s — real CSV of the tally table, no transcript echo |
| Convert to Markdown | ⊘ preflight | — | — | — |
| Group Same Documents | ⊘ preflight | — | — | — |
| Split Chapters | ⊘ "No PDF source" (sample is JPEGs) | — | — | — |
| Rotate / Prepare / Enhance / Remove BG / Fuzzy Clean / Split / Segment / Recombine (8 image ops, no model) | ✓ all, 4–19s each | n/a | n/a | n/a |

Cloud spend: 6 page-scale calls on openrouter gemini-3.1-flash-lite; zero
other paid calls. Ollama cloud models were quota-exhausted (correctly
classified as "Provider quota or rate limit reached" — the error taxonomy
works). The dedicated ollama pass is therefore an environment limit, not a
product verdict.

## Bugs found live and FIXED (each with a regression test, committed)

1. **`b240664df` — deterministic text cleaner destroyed diary prose.**
   Four data-destroying passes in `TextCleaner` (the DEFAULT Clean Up Text
   path): any 20+ word unpunctuated run was deleted wholesale (a legitimate
   26-word diary sentence → empty string); `.*?phrase.*?` + DOTALL wrapper
   stripping swallowed everything before a mid-line "Note:"; a global 5-gram
   seen-set deleted recurring diary formulae ("Went to church in the
   morning" on a later day lost); legitimate doubles ("that that",
   "had had") were collapsed. All confirmed on Marshall text, all fixed
   conservatively (repetition-only pathological pruning, line-start-only
   wrapper stripping, adjacent-only phrase dedupe, whitelist for legit
   doubles, and line structure preserved instead of paragraph-izing).

2. **`5739e05d8` — five presets never wired `documents` into their
   text node.** Translate failed EVERY run at the save step ("nothing to
   attach the result to"); Clean Up Text failed SILENTLY — the programmatic
   path skips the save when documents is empty, so the run "completed" with
   no artifact. Swept the family: Clean Up Text, Translate, Translate
   (DeepL), Extract Geo, Translate + Double-Check all fixed
   (`files-source.documents → node.documents`; the review node uses the
   static inputs mapping per the single-inbound-edge rule #837);
   `preset_version` bumped so existing libraries heal. The DeepL `translate`
   tool also never declared the `documents` port its body reads — now merges
   `BASE_INPUT_PORTS`. Guard test added for the whole class.

3. **`11e2ab27d` — node-cache hits lost their text.** `NodeCache.get`
   returns a `CacheEntry` wrapper; the parallel fan-out fed the WRAPPER into
   `parallel_results`, the aggregator's `isinstance(result, dict)` missed
   every field, and a cache hit "completed" with `text=""` — the next node
   died with "No text provided". Every second run of
   Transcribe/Clean Up Text/Translate hit this. The poisoned-empty-entry
   guard (#834) was equally blind (`bool(entry)` is always True). Regression
   test runs the shipped Transcribe preset twice and pins the second run's
   text; verified to fail on the unfixed builder.

4. **`f84302ba9` + `7f1b5bfbd` — managed oMLX health checks never matched
   the real mlx_lm server.** (a) The absolute `/health` path was joined
   UNDER `/v1` → `/v1/health`, which the real server 404s. (b) The real
   server's payload is just `{"status": "ok"}`; the rich-shape parser
   defaulted `model_loaded=False`, so a ready runtime sat permanently
   "degraded". Both halves were green in CI because the unit fake accepted
   both URLs and spoke a richer dialect than the real server — the fakes now
   match real granularity.

5. **`ddf4232b7` — oMLX stop 500ed across event loops.** The asyncio
   subprocess handle is bound to the loop that spawned it (a workflow run's
   loop, via on-demand start); the stop endpoint runs on the API loop and
   raised "got Future … attached to a different loop", leaving the manager
   stuck on a stale healthy pid. `stop()` now falls back to
   SIGTERM→SIGKILL by pid.

6. **`ce36b9969` — 5s cold-start budget for an 8B model.** The per-probe
   health timeout (5s) doubled as the whole startup deadline, so every
   on-demand oMLX cold start failed its triggering run and succeeded on
   manual retry. New `startup_timeout_seconds` (120s) bounds startup;
   verified live — the first workflow after an engine restart now waits out
   the model load and completes.

7. **`49bdad4eb` — cleanup prompt tune (measured).** See next section.

## Transcript-cleanup quality (before/after, with evidence)

Evidence files: `agent-work/design/workflow-exercise/cleanup-compare/`.

**Programmatic cleaner, old vs fixed** (20 Marshall reference transcripts,
`old-vs-new-cleaner.txt`): the old cleaner's worst case kept 73% of a page —
it deleted the entire Tuesday Jan 9 entry ("TUESDAY, ." is all that
survived); the fixed cleaner keeps 99% and that entry verbatim. Aggregate
retention 93% → 94%, but the old 93% included pages where whole entries
vanished while whitespace inflation masked the loss.

**Does the small-model LLM cleanup actually improve text?** Yes — with the
local Qwen3-VL-8B (omlx), measured on real Apple-OCR output
(`input_*` vs `programmatic_*` vs `llm_engine_*`):
- The LLM fixes real OCR misreads the programmatic pass cannot:
  `CAPRICORNT→CAPRICORN`, `SAGITTARIUST→SAGITTARIUS`, `VIRCO→VIRGO`,
  `Sh. Saw Pabl→Sh. Saw Pablo`, and drops duplicated partial lines
  (`Y, JANUARY 5` next to `FRIDAY, JANUARY 5`) — with no content loss.
- The programmatic pass dropped `63-B64 -` (possibly a claim/dredge
  number) via its digit-soup filter; the LLM kept it. For archival material
  the LLM path is the more meaning-preserving of the two.
- **Prompt tune**: the default prompt made the model emit markdown hard
  line breaks — every line ended in a trailing double-space, plus added
  blank lines. Appending a plain-text instruction (no markdown, no trailing
  spaces) took trailing-whitespace lines from ~100% to 0 with identical
  corrections (`llm_omlx_b0dd.txt` vs `llm_tuned_b0dd.txt`). That
  instruction is now part of the default prompt (`49bdad4eb`).

Recommendation kept OUT of code (needs a ruling): the Clean Up Text preset
still defaults to `cleaning_method: programmatic`. With the destroyers
fixed it is safe, but the LLM mode on a free local model is measurably
better on OCR noise; consider flipping the preset default once a local
model is reliably provisioned.

## Findings NOT fixed (need a ruling or bigger work)

- **Local MLX vision is not actually possible today.** The provisioned
  runtime is `mlx_lm server` (0.31.3), which rejects image content
  ("Only 'text' content type is supported"). Every vision workflow on
  provider `omlx` fails regardless of the VL model name. Serving
  Qwen3-VL's vision path needs `mlx-vlm` (or an omlx server that speaks
  it). Until then the "local-first vision" story is Apple Vision OCR only.
- **Fresh-install defaults can't run a third of the presets.** With pure
  Apple defaults (a new library, nothing configured), Auto-Detect,
  Describe, Extract Table, Detect Regions (VLM), Convert to
  Markdown/HTML/SVG and Group Same Documents all refuse (correctly, with
  good messages) because Apple Vision is recognition-only and
  apple-intelligence isn't accepted for those vision steps. The errors are
  excellent; the out-of-box experience still fails. Options: route
  classify/describe-class steps to Apple Intelligence where it can serve,
  or surface the preflight verdict in the workflow list before run time.
- **Vision-tier UX pitfall.** Detect Regions (VLM) resolves the
  `$vision_medium` tier, not the headline vision default — setting
  "Vision" to a VLM while `vision_medium` still says Apple Vision keeps the
  preset refusing. Easy to hit, confusing to diagnose.
- **`error_kind` is embedded in error STRINGS** (`[kind]` from
  `classify_vision_failure`, and classified wrapper prefixes like
  "Provider quota or rate limit reached"), not a structured field on the
  thread status — the driver could not record it as a column. If the matrix
  is to be machine-tracked, the thread status payload should carry it.
- **Ollama cloud quota** was exhausted (all of the installed ollama models
  are `:cloud` relays); no local ollama weights are present, so the ollama
  lane is untested beyond error classification.
- The stop-route 500 also surfaced a starlette middleware noise cascade in
  the log; benign after the loop fix but worth remembering when reading old
  logs.

## Where things live

- Scratch env (safe to delete): `~/code/fichero-worktrees/.workflow-exercise/`
  (`Scratch.fichero`, isolated engine state, engine.log, cleanup-compare
  originals). A copied cert dir `Remote Access/127.0.0.1-8767-workflowex/`
  exists for CLI pinning to the spare port.
- Driver: `scripts/exercise_workflows.py` (extends the exercise family;
  `exercise_tools.py` untouched and still the per-tool prover).
- Raw run JSON + cleanup evidence: `agent-work/design/workflow-exercise/`.

## Commits (this exercise)

- `b240664df` fix(cleanup): stop the deterministic text cleaner destroying diary prose
- `5739e05d8` fix(workflows): wire source documents into every doc-persisting text preset node
- `11e2ab27d` fix(workflows): unwrap CacheEntry on node-cache hits — a hit was losing its text
- `f84302ba9` fix(llm): managed oMLX health check hits /health at the server root, not /v1/health
- `7f1b5bfbd` fix(llm): accept mlx_lm's bare {"status": "ok"} health payload as healthy
- `ddf4232b7` fix(llm): oMLX stop survives cross-loop subprocess handles via pid signals
- `ce36b9969` fix(llm): give managed oMLX a real cold-start budget (120s), not the 5s probe timeout
- `49bdad4eb` tune(cleanup): LLM cleanup prompt demands plain text — no markdown, no trailing spaces
