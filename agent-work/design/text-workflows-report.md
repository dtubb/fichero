# Text Workflows Report — TRANSCRIBE / CLEAN UP / TRANSLATE / DESCRIBE (2026-09-03)

Systematic end-to-end exercise of the four text workflow families on real
Marshall 1923 diary pages, continuing the 2026-09-02 overnight program
(`workflow-exercise-report.md`). Prior fixes (TextCleaner prose destruction
b240664df, documents wiring 5739e05d8, CacheEntry unwrap 11e2ab27d,
structured-call retry 08b2c490a) were re-verified, not re-fixed.

## Setup

- Engine: this worktree's code on isolated ports (8767 shared scratch from
  the overnight run; later `https://127.0.0.1:8770` with its own
  `FICHERO_BASE_PATH`/`FICHERO_TOKEN_DIR` + fresh `TextWF.fichero`, because a
  sibling lane kept restarting the 8767 engine and flipping the shared
  library's vision default mid-pass — rows below are labelled by what the
  settings snapshot actually says, not by intent).
- Sample: Marshall diary title page + two diary pages (copied from the
  read-only `~/code/marshall_diaries` source; `~/Fichero/*` untouched).
- Driver: `scripts/exercise_workflows.py`; raw rows in
  `agent-work/design/workflow-exercise/*.json` (`apple-20260903*`,
  `apple-pure*`, `tw-*`).

## Matrix — preset × model config

Legend: ✓ ran end-to-end and persisted its artifact · ✗→✓ defect found, root
cause fixed+tested tonight, re-verified green · ⊘ correct capability refusal
(wiring PASS) · — not run (budget) · (g) row ran under the leftover gemini
vision default, see caveat above.

| Preset | apple (vision+AI) | openrouter gemini-3.1-flash-lite | openrouter claude-sonnet |
|---|---|---|---|
| Capture OCR + Transcribe | ✗→✓ 79s (phantom node + wrong files; preset rewired, v2) | — | — |
| Transcribe | ✓ 99s | — | (see tw pass) |
| Transcribe (Auto-Detect) | ⊘ classify needs generative vision | ✓ (overnight, 11.6s) | — |
| Transcribe HTR | ✓ 65s | — | — |
| Transcribe Manuscript | ✓ 73s | — | — |
| Transcribe Typescript | ✓ 41s | — | — |
| Transcribe + Review (Pipeline) | ⊘ (sub-workflow review refusal, well-worded) | — | — |
| Transcribe Paleography | ✓ (g) | ✓ | — |
| Transcribe Paleography (Economy) | ⊘ cleanup pins $vision_small | — | — |
| English Secretary Hand / Paleografía ×2 / Latin | ✓ (g — generative transcription real) | ✓ | — |
| Paleographer Review | ⊘ on pure apple · ✓ (g) | ✓ | — |
| Clean Up Text (programmatic) | ✓ 18s, content preserved | n/a | n/a |
| Clean Up Text (LLM) | (tw pass) | (tw pass) | (tw pass) |
| Translate | ✓ 104s | (tw pass) | (tw pass) |
| Translate (DeepL) | ✗→ pro-key host fix (was 403 mislabelled "quota") | n/a (own provider) | n/a |
| Translate + Double-Check | ✓ 115s (one transient Apple GenerationError, passed on retry) | — | — |
| Translate the Reviewed Transcription | ✗→✓ 58s (datetime crash in state size probe) | — | — |
| Translate to English (Historical) | ✓ 241s | ✓ (g) | — |
| Modernización (Spanish) | ✓ (g) | ✓ | — |
| Regesto (Archival Abstract) | ⊘ on pure apple | ✓ (g) | — |
| Describe (visual) | ⊘ needs generative vision | ✓ describes the IMAGE | (tw pass) |

### Isolated env (`https://127.0.0.1:8770`, fresh `TextWF.fichero`, 3 Marshall pages)

| Preset | apple (pure) | gemini-3.1-flash-lite | claude-sonnet-5 (openrouter) |
|---|---|---|---|
| Transcribe | ✓ 43s (Apple OCR) | — | ✓ 27s — real HTR, keeps "B63-B64" |
| Clean Up Text (programmatic) | ✗→✓ (tally-page number destruction, fixed) | n/a | n/a |
| Clean Up Text (LLM) | ✓ 32s apple-intelligence | ✓ 28s | ✓ 34s faithful, zero loss |
| Translate | ✓ 34s | ✓ 52s (no trailing spaces — prompt tune verified) | ✓ 27s |
| Translate (DeepL) | ✗ env: the DEEPL_API_KEY in the shell is dead (403 on BOTH DeepL hosts, probed directly) — now correctly reported as "Provider authentication failed. Update API key in Settings" instead of "quota…top up account" | n/a | n/a |
| Transcribe (Auto-Detect) | ⊘ | ✓ 39s | — |
| Describe (visual) | ⊘ | ✓ 30s — describes the image (ledger layout, binding, paper) | ✓ 23s — image-grounded, layout + hands |

`anthropic/claude-sonnet-5` resolves and answers through the openrouter
provider route (`workflow preview-cost` names it per node; runs green).
Cloud spend: ~6 gemini flash-lite page-calls + ~5 sonnet page-calls on this
env, plus the unintended gemini-hybrid rows on the shared env.

## Defects found live and FIXED (each with a regression test, committed)

0. **Programmatic cleaner deleted every number on a tally page.** The
   per-line "short pure number = page noise" drop erased all counts on the
   Marshall dredge-tally page (310→257 chars) while reporting success.
   `remove_ocr_garbage_lines` now detects a tabular page (≥5 tally-shaped
   lines and ≥30% of the page) and keeps its numbers; prose pages keep the
   old behaviour. Digit blobs ("290029090") stay classified as soup.
   (`text_cleaning.py`, tests on both page shapes)

1. **CLI `--wait` died on dropped keep-alive connections.** uvicorn expires
   idle keep-alives (~5s; sooner when the engine loop is busy with local
   inference); httpx surfaced the reuse as `RemoteProtocolError("Server
   disconnected without sending a response")` and every poll of a busy run
   reported `cli_error` for runs that completed. GETs now retry exactly once
   on a fresh connection; non-GETs never retry.
   (`fichero-cli/client.py`, `test_client_keepalive_retry.py`)

2. **Capture OCR + Transcribe transcribed the WRONG file, twice.** The
   preset's transcribe node (a PARALLEL tool) had inbound edges from both
   the files source and enhance_images; any source-tool edge arms per-file
   fan-out regardless of port, so it transcribed the ORIGINAL upload before
   prepare/enhance ran, and the chain edge then fired the Send-expecting
   `_process` node with no payload (`[PARALLEL] [1/1] FAILED: File not
   found:` on an empty path) — while the run still said "completed
   successfully". Rewired per the single-inbound-edge rule (#837): documents
   via static inputs mappings, one edge (enhance.output_files → files),
   preset v2. New repo-wide guard `test_preset_parallel_edge_rules.py`
   forbids the mixed fan-out/chain shape and self-tests on the original
   broken wiring. Verified live: enhance completes BEFORE transcribe, one
   invocation, green.

3. **'Translate the Reviewed Transcription' crashed on datetime.** The state
   size probe (`compact_output_for_state`) used strict `json.dumps`;
   artifacts_source outputs carry `created_at` datetimes → TypeError killed
   the run before its first LLM call. The probe is an estimate, not a
   serialization contract: `default=str`. Verified live green.

4. **Translate (DeepL) 403'd every run — and blamed billing.** Two halves:
   the free host `api-free.deepl.com` was the unconditional default, wrong
   for Daniel's PRO key (free keys end `:fx`); and `builder._is_quota_error`
   matched the bare substring "403", so the auth failure surfaced as
   "Provider quota or rate limit reached. Top up account…". Host now follows
   the key type; quota detection delegates to the LLM error taxonomy (quota
   wording required for 403s; "key limit" added). Stale tests pinning
   bare-403=quota were updated to the new spec.

5. **Translation prompt tune (same class as 49bdad4eb).** Apple Intelligence
   translations ended every line in a trailing double-space (markdown hard
   breaks). The clean_text plain-text rule now rides in text_translate's
   always-present fidelity block.

## Quality spot-checks

- **Clean Up (programmatic), title page**: nothing destroyed; short OCR
  fragments merged/deduped; garbage like `VIRCO.` correctly left (it only
  fixes what it can prove). Consistent with the post-b240664df behaviour.
- **Translate (apple)**: English→English echo is faithful and actually
  repairs OCR noise (CAPRICORNT→CAPRICORN, dedupes split lines); trailing
  double-spaces on every line → prompt tune (fix 5).
- **Describe**: on a generative vision model the description is of the
  IMAGE ("title page of a vintage diary…", "frayed mesh binding", per-entry
  layout), not a transcript echo; pure Apple correctly refuses.
- **Clean Up LLM vs programmatic, tally page**: the LLM pass (any of the
  three models) keeps every count and fixes misreads (frun→from,
  Quildo→Quibdó via re-transcription); the programmatic pass deleted the
  numbers until fix 0. One nit: the gemini LLM clean dropped the standalone
  "1922" year header — the year-preservation rule may be worth adding to
  the cleanup prompt if it recurs.
- **Sonnet transcription** of a handwriting page is a genuine HTR upgrade
  over Apple OCR (keeps "B63-B64", correct day structure) at ~27s/page.

## Open rulings / not fixed

- **Settings are library-scoped and shared runs collide.** Two lanes
  exercising one scratch library flip `vision_provider` under each other;
  rows must be read against the pass's settings snapshot. (Process note,
  not a product defect — but a per-run model override would remove the
  ambiguity.)
- **CLI accepts a short doc id for `workflow run` and the files source then
  fails** with "0 processable files … ids=['b0dd8e2f']". Either the CLI
  should resolve short ids like `docs get` does, or the error should say
  "pass the full document id".
- **Economy preset on fresh-install defaults** refuses at its
  `$vision_small` cleanup — same out-of-box story as the overnight report's
  fresh-install finding; needs the vision-tier ruling.
- **Apple Intelligence transient GenerationError** (FoundationModels code
  -1 / ModelManagerError 1013) failed one Translate+Double-Check run and
  passed identical inputs 30 min later. Environment flake; worth a retry
  ladder someday if it recurs.
- **`builder` still lets a plain edge target a `_process` node** — my guard
  keeps shipped presets out of the trap, but user-authored workflows can
  still draw the mixed shape; the builder should reject or join it (chain
  machinery, other lane).

## Commits (this exercise)

- `fix(cli): retry a GET once when a pooled keep-alive connection was dropped`
- `fix(workflows): state-size probe tolerates non-JSON values in node outputs`
- `fix(workflows): Capture OCR + Transcribe transcribes the ENHANCED files, once`
- `fix(llm): DeepL host follows the key type; a bare 403 is auth, not quota`
- `tune(translate): translation prompt demands plain text`
