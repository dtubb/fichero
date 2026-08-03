# #4501 phase 2 — costed estimate for all 39 presets

**For Daniel to approve or decline.** Produced by `workflows/provider_preview.py`.
**Nothing was executed. No provider was contacted. This document cost nothing.**

## The headline

Identical files, opposite answers, because the answer lives in the database:

| configuration | free | billable |
|---|---|---|
| factory defaults — what a NEW install gets | **37 of 39** | 1 (+1 unknown) |
| this machine's app DB (`openrouter` / `gemini-3-flash-preview`) | **13 of 39** | 25 (+1 unknown) |

**24 presets change answer between those two rows.** Nothing in their JSON differs.

## ⚠️ SURPRISES — billable AND invisible from the preset

**This is the section that matters.** These presets bill on this machine while
their JSON says nothing whatsoever about a provider. Reading the file tells you
nothing; the app database decides, silently.

This is the exact shape that cost money twice on 2026-08-03 — once from a probe
expected to be on-device, once from a triage that classified presets as free by
reading their JSON. **25 of 39 presets are in this state.**

| preset | surprise nodes | resolves to | decided by |
|---|---|---|---|
| **Catalogue** | 10 | `openrouter` | `app_db` |
| **Transcribe (Auto-Detect)** | 7 | `openrouter` | `app_db` |
| **Transcribe Paleography (Ensemble + Deep Review)** | 6 | `openrouter` | `app_db` |
| **Spanish Script v2 Child Passes (19th-20th C.)** | 3 | `openrouter` | `app_db` |
| **Translate + Double-Check** | 3 | `openrouter` | `app_db` |
| **Clean Up Text** | 2 | `openrouter` | `app_db` |
| **Extract Geo** | 2 | `openrouter` | `app_db` |
| **Transcribe HTR** | 2 | `openrouter` | `app_db` |
| **Transcribe Paleography** | 2 | `openrouter` | `app_db` |
| **Translate** | 2 | `openrouter` | `app_db` |
| **Capture OCR + Transcribe** | 1 | `openrouter` | `app_db` |
| **2 · Extract Entities** | 1 | `openrouter` | `app_db` |
| **3 · Extract SVO → Claims** | 1 | `openrouter` | `app_db` |
| **6 · Catalogue** | 1 | `openrouter` | `app_db` |
| **Convert to HTML** | 1 | `openrouter` | `app_db` |
| **Convert to Markdown** | 1 | `openrouter` | `app_db` |
| **Convert to SVG** | 1 | `openrouter` | `app_db` |
| **Describe (visual)** | 1 | `openrouter` | `app_db` |
| **Extract Table** | 1 | `openrouter` | `app_db` |
| **Group Same Documents** | 1 | `openrouter` | `app_db` |
| **NER per-page (local)** | 1 | `openrouter` | `app_db` |
| **Transcribe** | 1 | `openrouter` | `app_db` |
| **Transcribe Manuscript** | 1 | `openrouter` | `app_db` |
| **Transcribe Typescript** | 1 | `openrouter` | `app_db` |
| **Translate (DeepL)** | 1 | `openrouter` | `app_db` |

**Totals on this machine:** 61 calls/page ≈ $0.1921/page ≈ **$19.21 per 100 pages**.

## The three-way split

### A — free under ANY configuration (13)

No node resolves a provider. The only presets whose cost is a property of the FILE.
All 13 carry `tested`, and the sets match exactly.

| preset | model nodes | calls/page | `tested` |
|---|---|---|---|
| 1 · Import → Artifacts | 0 | — | **yes** |
| 4 · Merge / Dedup | 0 | — | **yes** |
| 5 · KG Persist / Finalize | 0 | — | **yes** |
| Enhance Images | 0 | — | **yes** |
| Export to Desktop (MD + DOCX + XLSX) | 0 | — | **yes** |
| Fuzzy Clean Images | 0 | — | **yes** |
| Prepare Images for OCR | 0 | — | **yes** |
| Recombine Segments | 0 | — | **yes** |
| Remove Background Images | 0 | — | **yes** |
| Rotate / Auto-Orient Images | 0 | — | **yes** |
| Segment Images | 0 | — | **yes** |
| Split Chapters | 0 | — | **yes** |
| Split Images | 0 | — | **yes** |

### B — free ONLY on factory defaults (24)

Free on a new install. **Every one of these bills on this machine.**

| preset | model nodes | calls/page | $/page | $/100 pages | `tested` |
|---|---|---|---|---|---|
| 2 · Extract Entities | 1 | 1 | $0.0032 | $0.32 | no |
| 3 · Extract SVO → Claims | 1 | 1 | $0.0032 | $0.32 | no |
| 6 · Catalogue | 1 | 1 | $0.0032 | $0.32 | no |
| Capture OCR + Transcribe | 1 | 1 | $0.0032 | $0.32 | no |
| Catalogue | 10 | 10 | $0.0315 | $3.15 | no |
| Clean Up Text | 2 | 2 | $0.0063 | $0.63 | no |
| Convert to HTML | 1 | 1 | $0.0032 | $0.32 | no |
| Convert to Markdown | 1 | 1 | $0.0032 | $0.32 | no |
| Convert to SVG | 1 | 1 | $0.0032 | $0.32 | no |
| Describe (visual) | 1 | 1 | $0.0032 | $0.32 | no |
| Extract Geo | 2 | 2 | $0.0063 | $0.63 | no |
| Extract Table | 1 | 1 | $0.0032 | $0.32 | no |
| Group Same Documents | 1 | 1 | $0.0032 | $0.32 | no |
| NER per-page (local) | 1 | 1 | $0.0032 | $0.32 | no |
| Spanish Script v2 Child Passes (19th-20th C.) | 3 | 3 | $0.0095 | $0.95 | no |
| Transcribe | 1 | 1 | $0.0032 | $0.32 | no |
| Transcribe (Auto-Detect) | 7 | 7 | $0.0221 | $2.21 | no |
| Transcribe HTR | 2 | 2 | $0.0063 | $0.63 | **yes** |
| Transcribe Manuscript | 1 | 1 | $0.0032 | $0.32 | no |
| Transcribe Paleography | 2 | 2 | $0.0063 | $0.63 | no |
| Transcribe Paleography (Ensemble + Deep Review) | 6 | 12 | $0.0378 | $3.78 | no |
| Transcribe Typescript | 1 | 1 | $0.0032 | $0.32 | no |
| Translate | 2 | 2 | $0.0063 | $0.63 | no |
| Translate + Double-Check | 3 | 3 | $0.0095 | $0.95 | no |

### C — billable under every configuration (1)

| preset | model nodes | calls/page | $/page | $/100 pages | `tested` |
|---|---|---|---|---|---|
| Translate (DeepL) | 2 | 2 | $0.0063 | $0.63 | no |

### U — UNKNOWN, cost lives in a delegated child (1)

| preset | model nodes | calls/page | `tested` |
|---|---|---|---|
| Transcribe Spanish Script (19th-20th C.) | 0 | — | no |


## Cost assumptions — stated, because they are assumptions

**Solid (derived, not estimated):**

- **Model nodes per preset** — from `ToolDef.uses_llm`, the tool's own
  declaration, which is what the runner itself consults.
- **Tile fan-out** — ×2 where a `zoom` node tiles the page. Confirmed against a
  real run: the paleography ensemble made **12** calls, not the ~8 estimated,
  because the review tiers send images too.
- **Provider and model** — resolved through the runner's own precedence.

**Assumed (a reader may reasonably disagree):**

- **1 page = 1 unit.** Multi-page documents multiply everything linearly.
- **~1,500 input tokens + ~800 output tokens per vision call.** A page image
  plus a transcription. This is the softest number here; it is not measured,
  and image tokenisation varies by provider. Costs scale linearly, so halve the
  assumption and halve the estimate.
- **Pricing** from litellm for `gemini-3-flash-preview`: $5e-07/input token,
  $3e-06/output token — i.e. **$0.00315 per call**. Real, not invented, but
  tied to the model this machine currently resolves to.
- **Retries are NOT counted.** A failing node retries; the paleography HTR
  failure burned several attempts per run. Treat these as floors.

## What to decide

1. **Group A (13) needs nothing.** Already validated, already `tested`, free
   under every configuration. No approval required.
2. **Group B (24) is free on a factory install.** If validation runs pinned to
   on-device defaults, phase 2 completes at **zero cost** — but see the caveat
   below, because pinning is harder than it looks.
3. **Only `Translate (DeepL)` genuinely requires spend** to validate, and it is
   one preset.
4. **`Transcribe Spanish Script` cannot be costed** until delegation is
   followed; it is reported UNKNOWN rather than guessed.

At the totals above, validating **every** billable preset once on a single page
costs roughly **$0.19** — 61 calls. The money is not the issue. The issue is
that nobody could see it coming, and now they can.

## Two caveats on "just pin it to on-device"

**Env pinning does not cover the majority case.** `FICHERO_<TIER>_PROVIDER`
only reaches `resolve_model_alias`, i.e. nodes naming a `$tier`. A node with NO
provider — most of them — goes to `app_db.get_default_model_for_category(...)`,
which never reads the environment. A guard built on env alone is incomplete,
and I know that because I built one and it would not have stopped the spend it
was written to prevent.

**The preview must be re-run on the machine that will do the validating.**
Every number in the "this machine" column is a property of THIS app database.
That is the whole finding, and it applies to this document too.

## Provenance

- Resolver: `fichero-server/src/fichero_server/workflows/provider_preview.py`
- Tests: `tests/unit/workflows/test_provider_preview.py` (18)
- Method: every node resolved through the runner's own
  `_resolve_node_llm_config_inner`; billability from the provider registry's
  `is_local`/`is_builtin`; unknown provider treated as billable, because if you
  cannot establish something is on-device, "free" is the expensive guess.
