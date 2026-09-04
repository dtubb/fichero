# The Grand Sweep — every workflow, tool and chain, across three model configs

2026-09-04. Lane `grand-sweep`, one sequential worker, worktree
`fichero-worktrees/integration`.

Daniel's mandate: *go through each workflow, tool and chain, with local,
OpenRouter and MLX models, on a few pages, and say how they are doing. Less is
more — the tools, models and workflows need to WORK. There are lots of tools;
some are old approaches. What do we keep, what do we get rid of? Are there
multiple transcription workflows? There seem to be duplicate workflows.*

This report answers those five questions. It **reuses** the night's evidence
rather than re-running it (six lane reports, listed under Sources) and adds the
gaps: the tools nobody exercised, the MLX column, the chains, the
drag-and-drop import path, and the synthesis.

**Nothing in the grooming proposal has been deleted.** Retirement is Daniel's
call; this lane recommends and shows its work.

---

## 0 · The shape of the thing, in numbers

| | count | note |
|---|---|---|
| Shipped workflow presets | **52** | `resources/default_workflows/*.json` |
| Preset folders | 12 | `resources/workflow_folders.json` |
| …of which **/Transcribe** | **15** | 29% of every preset is a transcription |
| Registered tools | **142** | `workflows/registry.list_tools()` |
| …executable | 126 | |
| …**palette stubs** (registered, not executable) | **16** | `to_pdf/to_word/to_excel/to_json`, `if/switch/loop/filter/merge`, `export/save_to_library`, `crop/enhance/rotate/segment`, `custom_llm` |
| …**used by no shipped preset** | **102** | many legitimately palette-only; 24 are orphans of a retired pipeline (below) |
| …carrying `tested=True` | **6 of 142** | the flag is vestigial, not a signal — see R-9 |
| Orchestration surfaces | 3 | presets · `sub_workflow` chains · `/api/chains` (workflow-bar chains) |

---

## 1 · Answering Daniel directly

**"Are there multiple transcription workflows?"** — Yes: **15 of 52 presets
live in /Transcribe.** Nine of them are the same tool (`transcribe`) with a
different prompt string:

| preset | vision_mode | thinking | what actually differs |
|---|---|---|---|
| Transcribe | auto | — | no prompt at all (provider default) |
| Transcribe Typescript | auto | — | printed/typed prompt |
| Transcribe Manuscript | auto | — | modern-handwriting prompt |
| Transcribe HTR | llm | long | historical-handwriting prompt |
| Transcribe Paleography | llm | long | paleographer prompt, script family auto-detected |
| English Secretary Hand (16th–17th C.) | llm | long | = Paleography, one guidance block swapped |
| Paleografía Española (s. XVI–XVII) | llm | long | = Paleography, one guidance block swapped |
| Paleografía Española (s. XVIII–XIX) | llm | long | = Paleography, one guidance block swapped |
| Latin Paleography | llm | long | = Paleography, one guidance block swapped |

Measured prompt similarity of the four language variants against
`Transcribe Paleography`: **0.63 – 0.71**. They are genuine specialisations
(real period/orthography guidance, not cosmetics) — but they are nine presets
where the user-visible decision is "what kind of hand is this?", which is
exactly the question `Transcribe (Auto-Detect)` already answers.

The other six in the folder are different shapes and all earn their place:
Auto-Detect (classify → route), Paleographer Review (3-pass review of an
existing transcription), Transcribe + Review (Pipeline) (sub-workflow chain),
Transcribe Paleography (Economy) (free Apple line boxes + cheap local HTR),
Capture OCR + Transcribe (prepare → enhance → transcribe), Prepare Images for
OCR (image prep only, no model).

**"There seem to be duplicate workflows."** — Two distinct causes, and only one
of them is a defect:

1. **Not stale rows.** I diffed every top-level preset `name` that has ever
   existed in the git history of `default_workflows/` (59 names) against the
   52 current names plus the 18 in `_DEPRECATED_PRESET_NAMES`: **zero orphans.**
   Every rename since the beginning is retired. A preset id is
   `uuid5(namespace, name)`, so a rename *does* mint a new row and strand the
   old one — the discipline of adding the old name to `_DEPRECATED_PRESET_NAMES`
   is what has kept that from happening, and it has held so far. It is a
   convention with no guard behind it (R-8).
2. **Real near-duplicates by design** — the nine transcribe variants above, and
   five translate-shaped presets split across two folders (see §4).

**"Some tools are old approaches."** — Three concrete ones, with evidence, in §5.

---

## 2 · The matrix — presets × model config

Columns: **Apple** = factory defaults, no keys (Apple Vision OCR +
Apple Intelligence) · **OR-flash** = openrouter `google/gemini-*-flash-lite`
(cheap cloud) · **MLX** = local managed sidecar (`mlx_vlm.server`,
Qwen2.5-VL-3B).

Legend: **✓** ran end-to-end and persisted its artifact · **✗→✓** failed, root
cause fixed and re-verified during this program · **⊘** correct, well-worded
capability refusal (wiring passes; the model cannot do the job) · **—** not run
· **✗** broken.

### /Transcribe (15)

| Preset | Apple | OR-flash | MLX | source |
|---|---|---|---|---|
| Transcribe | ✓ 43–99s | ✓ (sonnet 27s, real HTR) | ✓ 236s/page, Spanish page readable | text-wf, mlx-lane |
| Transcribe Typescript | ✓ 41s | — | — | text-wf |
| Transcribe Manuscript | ✓ 73s | — | — | text-wf |
| Transcribe HTR | ✓ 65s | — | — | text-wf |
| Transcribe Paleography | ✓ | ✓ | — | text-wf |
| English Secretary Hand | ✓ | ✓ | — | text-wf |
| Paleografía Española (XVI–XVII) | ✓ | ✓ | — | text-wf |
| Paleografía Española (XVIII–XIX) | ✓ | ✓ | — | text-wf |
| Latin Paleography | ✓ | ✓ | — | text-wf |
| Transcribe (Auto-Detect) | ⊘ classify needs generative vision | ✓ 11.6–39s | — | workflow-ex, text-wf |
| Paleographer Review | ⊘ on pure Apple · ✓ with a VLM | ✓ | — | text-wf |
| Transcribe + Review (Pipeline) *(chain)* | ⊘ sub-workflow review refusal, well-worded | — | — | text-wf |
| Transcribe Paleography (Economy) | ⊘ cleanup pins `$vision_small` | — | — | text-wf |
| Capture OCR + Transcribe | ✗→✓ 79s (phantom node, wrong file — preset rewired v2) | — | — | text-wf |
| Prepare Images for OCR | ✓ n/a model | n/a | n/a | workflow-ex |

### /Clean Up · /Translate · /Describe (6)

| Preset | Apple | OR-flash | MLX | source |
|---|---|---|---|---|
| Clean Up Text (programmatic) | ✗→✓ ×2 (prose destruction b240664df; tally-number destruction) | n/a | n/a | workflow-ex, text-wf |
| Clean Up Text (LLM) | ✓ 32s apple-intelligence | ✓ 28s | ✓ (Qwen3-VL-8B; prompt tuned 49bdad4eb) | text-wf, workflow-ex |
| Translate | ✗→✓ 34–104s (documents wiring 5739e05d8) | ✓ 52s | ✓ 52.7s | text-wf, workflow-ex |
| Translate (DeepL) | ✗→ host+error-taxonomy fix 43d9ad63d; key in Settings 170323d3d | n/a | n/a | text-wf |
| Translate + Double-Check | ✓ 115s | — | — | text-wf |
| Translate the Reviewed Transcription | ✗→✓ 58s (datetime crash 1f04651b7) | — | — | text-wf |
| Describe (visual) | ⊘ correctly refuses | ✓ 23–30s, describes the IMAGE | — | text-wf |

### /Extract (7) · /Organize · /Books · /Convert · /Export

| Preset | Apple | OR-flash | MLX | source |
|---|---|---|---|---|
| Diary Entries | ✓ 68.3s | ✓ 3 dated child entries | ✓ 37.2s | extract, workflow-ex |
| Extract Table | ⊘ preflight | ✓ 5.7s, real CSV of the tally table | — | workflow-ex |
| Extract Geo | ✗→✓ (documents wiring) | — | — | extract |
| Accounts → Spreadsheet (CSV) | ⊘ preflight | ✓ real CSV rows | — | extract |
| Regesto (Archival Abstract) | ✗→⊘ (was mid-run failure; now honest preflight) | ✓ | — | extract |
| Modernización (Spanish) | ✗→⊘ | ✗→✓ (was a 70ms silent no-op — d43a1d14b) | — | extract |
| Translate to English (Historical) | ✗→⊘ | ✗→✓ (same class) | — | extract |
| Group Same Documents | ⊘ preflight | ✗→✓ clusters + MOVES via audited actions (ad2e61b29) | — | extract |
| Split Chapters | ✓ (real PDF, TOC and heading bases) | n/a | n/a | extract |
| AI Convert to Markdown / HTML | ⊘ preflight | ✓ both | — | convert |
| AI Redraw as SVG | ⊘ preflight | ✓ well-formed, sanitized | — | convert |
| Export to Desktop (MD+DOCX+XLSX) | ✓ 65 files | n/a | n/a | convert |

### /Image Editing (7) + /Detect Regions (3) — no model involved except VLM

| Preset | verdict |
|---|---|
| Enhance · Fuzzy Clean · Remove BG · Rotate/Auto-Orient · Segment · Recombine · Split Images | ✓ all 7, 4–19s each, on Apple/no-model |
| Detect Regions (Apple Vision) | ✓ 15.3s, free, on-device |
| Detect Regions (VLM) | ⊘ on Apple (needs generative vision) · ✓ on OR-flash *(resolves `$vision_medium`, not the headline Vision default — R-4)* |
| Backfill Text Geometry | ✓ 5 of 6 real pages merge, hit_rate 1.00; the 6th refuses correctly |

### /Catalogue (8) — the chain

`Catalogue` (v6) is now literally the chain of the six numbered stage presets,
run as `sub_workflow` nodes joined by ordering edges.

| Config | result |
|---|---|
| Apple-only | ✓ whole chain, 94.8s; stage 6 empty-prompt defect found and fixed |
| OR-flash | ✓ all six stages; stage 6 tripped the 600s hang guard under load-214, degraded cleanly, standalone re-run green |
| Sonnet (via OpenRouter) | ✓ all six, 35.5s; keywords call exposed a sibling empty-prompt bug — fixed |
| NER per-page (local) | ✓ Apple 448s · ✓ MLX 17.5s |

**Provider-tolerance lesson worth keeping:** the empty-user-prompt defect was
*rejected* by Apple and Anthropic and *silently tolerated* by Gemini. A
one-provider matrix would have shipped it. This is the argument for the
three-column matrix existing at all.

---

## 3 · The 142 tools — what each class is doing

| Class | n | Verdict |
|---|---|---|
| Local image ops, no model by design | 13 | **WORKS.** enhance/fuzzy_clean/prepare/recombine/remove_background/rotate/segment/split_images/zoom + denoise/deskew/adaptive_binarize/auto_crop. The last four have no preset. |
| Apple OCR path | 4 | **WORKS.** detect_regions, economy_htr, transcribe, extract (after the all-files-failed fix) |
| Apple text/chat | 9 | **WORKS.** sentiment, summarize, summarize_file, rewrite, translate, text_translate(_review), timeline, questions |
| Deterministic text passes | 4 | **WORKS**, passthrough by design: clean_text, ocr_cleanup, text_reflow, consistency-check |
| Generative vision | 19 | **HONEST REFUSAL** on Apple (`requires_generative_model`, pre-dispatch, standard message); verified **✓ green** on flash-lite/Sonnet for convert + table_extract |
| KG / catalogue stages | 8 | **WORKS** — proven three-provider by the chain runs |
| `*_extract` / `*_page_cleanup` / `*_folder_cleanup` section family | **24** | **ORPHANED** — see R-1 |
| Agent tools (react/supervisor/swarm/coordinator/cli_agent) | 5 | **UNPROVEN.** Real implementations (343 + 230 LOC), no preset, no test, no live evidence anywhere in the night's work |
| Research tools (web_search, browser_navigate, document_fetch) | 3 | **UNPROVEN.** 765 LOC; `wait_for` documented as "not implemented yet — placeholder" |
| Audio / video | 2 | **UNPROVEN.** No preset, no exercise row |
| **Palette stubs** | **16** | **STUB.** Registered so the palette shows them; not executable. Recorded in the 2026-08-27 audit and still there. |

### Tool-level defects found and fixed during this program

- `extract`: an all-files-failed run reported **ok** with empty text, errors
  buried in `results[]`. Now carries a top-level `error`; partial failure stays ok.
- Prompt-shaped tools (`analyze`, `table_extract`) reused **another preset's
  artifact** as their own result, because skip-if-done keys on
  `(document, artifact_type, provider, model)` and never the prompt. Three paleo
  presets share `analyze`/`analysis`; after one Regesto run the other two
  "completed" in ~70ms returning the Regesto text verbatim. Both tools now opt
  out of skip-if-done. **This is the worst class of bug in the system: a
  successful-looking run that wrote nothing.**
- `analyze` refused apple-vision **mid-run** rather than at preflight.
- `similarity` failed a whole run because the model scored 0–100 and the model
  bound was `le=1.0`. Percentage scale now normalises.
- Exports silently dropped every entity/claim with **no source document** (hand-created
  via MCP or agent chat): the seeded library's 3 entities exported as **0 rows**.

---

## 4 · The three orchestration surfaces

1. **Presets** — the 52 JSON graphs. The primary surface. Healthy.
2. **`sub_workflow` chains** — a preset whose nodes are other presets. Two ship:
   `Catalogue` (6 stages) and `Transcribe + Review (Pipeline)` (2). Both work;
   the LangGraph fan-in join is what guarantees stage N+1 waits for stage N.
   This is the right chaining mechanism and it is proven three-provider.
3. **`/api/chains`** — a *second*, older orchestration API (1262 LOC of routes +
   841 LOC of `execution/chaining.py`), reached from the workflow bar via
   `ChainService`. **Live and wired** (WorkflowBarChainPersistence,
   ContentView+WorkflowChainEngine), user-created only — nothing seeds a
   default chain. Keep, but see R-2 for the dead endpoint inside it.

---

## 5 · Grooming proposal — KEEP / MERGE / RETIRE

Recommendations only. Nothing here has been changed. Each row carries the
evidence that produced it.

### R-1 · RETIRE: the 24-tool section-extract/cleanup family

`people_extract`, `places_extract`, `organizations_extract`, `events_extract`,
`dates_extract`, `keywords_extract`, `quotes_extract`, `citations_extract`,
`citation_usage_extract`, `hermeneutics_extract`, `legal_references_extract`,
`mines_extract`, `rivers_extract`, `properties_extract`, `book_index_extract`
plus the twelve `<type>_page_cleanup` / `<type>_folder_cleanup` tools.

*Why they exist:* they were the per-section machinery of the **Catalogue
monolith**, which Daniel replaced with the numbered 1–6 stage chain. The new
chain uses `extract_entities_only` / `extract_svo_only` / `merge_dedup_only` /
`kg_persist_finalize` instead.

*Evidence:* referenced by **no shipped preset**; the only non-definition
references are a suffix match in `cache.py` and a `_skip_sections` list inside
`extract_all.py`. The `<type>_clean` folder artifacts they wrote are recorded in
the catalogue lane's report as **intentionally dropped by Daniel's ruling**.

*Recommendation:* **RETIRE**, in one commit, after a live-caller sweep (the
`find_dead_code` import-graph is blind to `@register_tool`, so verify by direct
reference search, not the tool). Keep `citations_extract` under review — the
catalogue restructure noted citations as a capability that was dropped and may
need a home.

*Risk:* a user-authored workflow in an existing library could reference one.
Retirement should leave the tool resolvable-with-a-message rather than crashing
an old graph.

### R-2 · RETIRE: `/api/chains/presets/paleography` (GET + POST)

Builds "a stageable A/B/C paleography chain" — the **cross-model ensemble**
that Daniel explicitly retired on 2026-08-26 ("single model per run, review as
a standalone act"). Its preset counterpart, *Transcribe Paleography (Ensemble +
Deep Review)*, is already in `_DEPRECATED_PRESET_NAMES`; the endpoint that
rebuilds the same idea was left behind.

*Evidence:* no hand-written Swift caller (it appears only in the generated
client, the generated CLI surface, its own unit test, and the UI-wiring
**allowlist** — i.e. explicitly permitted to be unwired).

*Recommendation:* **RETIRE** both routes + `_build_paleography_chain` +
`PaleographyPresetResponse`; regenerate OpenAPI and the Swift/CLI clients in
the same commit. ~120 LOC and two endpoints off the public surface.

### R-3 · MERGE: `text_reflow` + `ocr_cleanup` into `clean_text`

*Evidence:* `clean_text` already exposes `fix_hyphenation`,
`reflow_paragraphs`, `strip_artifacts` and `fix_ocr` as toggles that drive the
shared, hardened `text_passes` module. `text_reflow.py` (257 LOC) and
`ocr_cleanup.py` (175 LOC) implement their **own** regex dehyphenation, reflow
and stamp-stripping and import nothing from `text_passes`. Neither is used by
any preset.

I ran all three over the five real Apple-OCR Marshall pages in
`cleanup-compare/`: **the outputs are equivalent and none is destructive**
(retention 1.00 across the board; `ocr_cleanup` grows the text slightly by
rejoining columns). So this is a duplication argument, not a correctness one —
but it means tonight's two data-destruction fixes to `text_passes` did not, and
could not, reach the other two implementations.

*Recommendation:* **MERGE** — keep `clean_text` as the one text-cleanup tool;
either retire the other two or reduce them to thin wrappers over `text_passes`
so a fix lands once. 432 LOC of parallel regex goes away.

### R-4 · FIX (small, UX): the vision-tier trap

*Detect Regions (VLM)* and *Transcribe Paleography (Economy)* resolve
`$vision_medium` / `$vision_small`, **not** the headline Vision default. Setting
"Vision" to a VLM while the tier still says Apple Vision leaves the preset
refusing, with a message that names the capability but not the setting to
change. Easy to hit, hard to diagnose — Daniel has hit exactly this class of
thing before.

*Recommendation:* the refusal message should name the **tier alias it
resolved** and the setting that governs it. One string, real relief.

### R-5 · RULING NEEDED: nine transcribe presets → one, with a "hand" option

*Recommendation (to Daniel, not shipped):* keep **Transcribe** (no prompt),
**Transcribe (Auto-Detect)** (the router), **Transcribe Paleography** with a
`script_family` config enum (`auto | english-secretary | spanish-early-modern |
spanish-modern | latin`), and **Transcribe Typescript / Manuscript / HTR**.
That retires four presets into one option, and — crucially — collapses five
copies of a 40-line prompt into one.

*Counter-argument, honestly:* named presets are discoverable in a way a config
enum is not; a paleographer scanning the sidebar for "Latin" finds it. If
discoverability wins, keep the nine and fix R-6 instead.

### R-6 · FIX (small, real): five copies of the same prompt

`transcribe_auto_detect.json` embeds **byte-identical** copies of the
typescript, manuscript, HTR and paleography prompts (measured similarity
**1.000** on all four) and a 0.937 near-copy of the Paleographer Review pass-1
prompt. Tonight's two prompt tunes (`49bdad4eb`, `6a1ca277a`) each had to be
applied in more than one place, and the review prompt has *already* drifted.

*Recommendation:* either a shared prompt fragment resolved at seed time, or a
guard test pinning "the auto-detect copy equals its source preset's prompt" so
drift fails the gate instead of shipping quietly.

### R-7 · RULING NEEDED: the five translate-shaped presets across two folders

`/Translate` holds Translate, Translate (DeepL), Translate + Double-Check,
Translate the Reviewed Transcription. `/Extract` holds **Translate to English
(Historical)**. The extract lane already flagged that the three paleography
*derivations* (Regesto, Modernización, Translate Historical) are **readings,
not extraction**, and live in /Extract only so nothing was orphaned by the
Extract-Data merge.

*Recommendation:* if a **/Paleography** family is approved, move all three —
three `folder_path` lines and three version bumps. Until then a user looking for
"translate" finds four of five.

### R-8 · GUARD: renames strand rows, and only a convention prevents it

A preset id is `uuid5(namespace, name)`. Rename a preset without adding the old
name to `_DEPRECATED_PRESET_NAMES` and every existing library shows **two rows
forever**. The history is currently clean (59 historical names, 0 orphans) — by
discipline alone.

*Recommendation:* a gate test that reads the shipped names and a committed
`retired_preset_names.json`, and fails when a name disappears from the shipped
set without appearing in the retired set.

### R-9 · The `tested` flag is dead metadata

**6 of 142** tools carry `tested=True`. Either populate it from this program's
evidence (the exercise harnesses now produce exactly that data) or delete the
field. A flag that is false for 96% of rows teaches readers to ignore it.

### R-10 · KEEP, with a note

- **The 16 palette stubs.** They are a UI promise the engine does not keep
  (`if`/`loop`/`filter`/`merge` especially — a user builds a branch and it does
  nothing). Recommend either implementing the five logic nodes or removing them
  from the palette; a stub that looks like a feature is worse than an absence.
- **Agent + research + audio/video tools (10).** Real implementations, zero
  evidence. Recommend one exercise pass before the next release rather than
  retirement — they may simply be untested rather than broken.
- **The four unpresented image ops** (denoise, deskew, adaptive_binarize,
  auto_crop_border). Working local tools with no preset. Cheap win: one
  "Clean Up Scans" preset would surface all four.

### Summary table

| Item | Verdict | One line |
|---|---|---|
| 24 `*_extract` / `*_cleanup` section tools | **RETIRE** | orphans of the retired Catalogue monolith; no preset, no caller |
| `/api/chains/presets/paleography` | **RETIRE** | rebuilds an ensemble Daniel retired; no hand-written caller |
| `text_reflow`, `ocr_cleanup` | **MERGE** into `clean_text` | 432 LOC duplicating the hardened `text_passes` |
| 4 language paleography presets | **MERGE** (ruling) | one preset + `script_family` enum, or keep for discoverability |
| Auto-Detect's 4 embedded prompt copies | **FIX** | share the fragment or guard the copy |
| 3 paleo derivations in /Extract | **MOVE** (ruling) | they are readings; /Paleography is their home |
| 16 palette stubs | **DECIDE** | implement the 5 logic nodes or take them out of the palette |
| 10 agent/research/AV tools | **KEEP, prove** | real code, zero evidence |
| 4 unpresented image ops | **KEEP, surface** | one "Clean Up Scans" preset |
| `tested` field | **FIX or DELETE** | true for 6 of 142 |

---

## 6 · Translation, end to end

Daniel on build 1: *"I tried to run translation and it never worked."* He was
right, and there were **four** independent reasons, all fixed in the last
24 hours and all present in this tree (verified: every SHA below is an
ancestor of HEAD).

| # | Root cause | Fix | Symptom Daniel saw |
|---|---|---|---|
| 1 | The translate node never received `documents`, so the save step had "nothing to attach the result to" — **every** run failed at the end | `5739e05d8` | ran, then failed |
| 2 | The node cache returned a `CacheEntry` wrapper into `parallel_results`; the aggregator's `isinstance(result, dict)` missed every field, so a cache hit completed with `text=""` and the next node died with "No text provided" | `11e2ab27d` | **every second run** failed |
| 3 | *Translate the Reviewed Transcription* crashed before its first LLM call — the state-size probe used strict `json.dumps` and `artifacts_source` outputs carry `created_at` datetimes | `1f04651b7` | that preset never ran at all |
| 4 | *Translate (DeepL)* 403'd on every run and blamed **billing**: the free host was the unconditional default (wrong for a PRO key) and `_is_quota_error` matched the bare substring "403" | `43d9ad63d` + `170323d3d` (key moved into Settings) | "top up your account" on a paid account |

Plus a quality tune: Apple Intelligence ended every translated line in a
trailing double-space (markdown hard breaks). `6a1ca277a` puts the plain-text
rule in `text_translate`'s always-present fidelity block.

**Static re-verification on current code (this lane):** I checked the
`documents` port on every doc-persisting text node in all 52 shipped presets.
All five translate-family presets receive it — four by edge, *Translate +
Double-Check*'s review node by static inputs mapping (correct, per the
single-inbound-edge rule #837). The only node without it is `6 · Catalogue`,
which writes to the container rather than per-document and ran green on all
three providers.

**Live results already on the board** (text-workflows lane, on this code):
Translate ✓ Apple 34s / flash-lite 52s / Sonnet 27s; Translate + Double-Check
✓ 115s; Translate the Reviewed Transcription ✓ 58s; Translate to English
(Historical) ✓ 241s Apple, ✓ flash-lite; Modernización ✓; Regesto ✓.
**Translate (DeepL) cannot be verified live: the DEEPL_API_KEY in the shell is
dead** — probed directly, 403 on *both* hosts. The wiring was verified
separately; what remains is a working key, not a code change.

> Verdict: **the translate family works on current code.** Every path Daniel
> would have tried on build 1 had a real defect; all four are fixed with
> regression tests. The one path still unproven end-to-end is DeepL, and it is
> blocked on a credential, not on Fichero.

---

## 7 · Drag-and-drop PDF import

The gesture needs the app; the pipeline it triggers does not. What a Finder
drag actually lands on:

```
Finder drag → SidebarItemRow+DropHandlers / LibraryItemDropDelegate
            → ImportService.importFiles(urls:)
                 file      → importFile      → POST /api/ingest/file
                 directory → startFolderImport → POST /api/ingest/folder  (task + poll)
            → ingest/core.py: import_file_impl / import_folder_impl
            → post-ingest: queue_derivatives → pages, thumbnails, text layer, geometry
```

Two things worth recording from the code, because both were bugs Daniel felt:

- `importFiles` passes `extractText`/`autoEmbed` as `nil` and **omits** them, so
  the engine's documented defaults apply. They used to default to `false` in
  Swift, silently overriding the engine's `True` on every drag-drop — the
  first-run "search returns nothing because nothing is indexed" trap (#3276).
  This is the clients-render-server-decides rule in miniature.
- Tonight's two fixes both target the **0%-forever** import:
  `4ce243dbc` makes an unreadable source loud (`exists()` is not readability —
  a read against a network volume with expired Kerberos credentials *blocks
  uncancellably*, and two of those stop the two-worker derivative pool dead),
  and `ef5f50f89` makes the progress bar count **pages, not documents**
  (a single 252-page PDF had `total=1`, so the bar's only states were 0% and
  done, while its label said "pages" — six minutes of honest work reading as
  a hang). 33 tests across `test_import_stall_is_loud` +
  `test_post_ingest_derivatives`, verified by the manager.

---

## 8 · MLX, honestly

The local column moved twice in two days and the report should say where it
landed.

- **2026-09-02:** local MLX vision was *impossible*. The provisioned runtime
  was `mlx_lm server` 0.31.3, which rejects image content ("Only 'text' content
  type is supported"). Every vision workflow on provider `omlx` failed
  regardless of the VL model name. Local text workflows (Clean Up Text LLM,
  Translate, Diary Entries, NER) worked fine.
- **2026-09-03/04:** the sidecar now runs `mlx_vlm.server`, and vision **does**
  work: Qwen2.5-VL-3B transcribed a real Spanish manuscript page, and
  `analyze` / `caption` / `classify` / `classify_script` all returned genuine
  image-grounded answers.
- **But the sidecar dies.** In the tool sweep, the first four vision tools
  answered and then every subsequent tool returned
  `local inference process exited 3` in 0.1–0.3s. That is a sidecar crash
  mid-sweep, not a capability refusal — the tools were never given a chance to
  fail on their own merits. On a 16 GB Mac the 8B profile swap-deaths outright;
  the 3B survives longer but not a full pass.

**Verdict for the MLX column: LOCAL VISION WORKS, THE SIDECAR DOES NOT STAY
UP.** Until a run can complete a full pass without the process exiting, the
local-first vision story is *demonstrable* but not *dependable*. That is the
single highest-value MLX ticket, and it is bigger than this lane: it is memory
headroom and process lifetime, not a preset bug.

Five oMLX defects were found and fixed during this program and are worth
recording because they were all invisible to CI:

| Fix | What was wrong | Why CI was green |
|---|---|---|
| `f84302ba9` | `/health` was joined UNDER `/v1` → `/v1/health`, which the real server 404s | the unit fake accepted both URLs |
| `7f1b5bfbd` | the real server answers `{"status": "ok"}`; the rich-shape parser defaulted `model_loaded=False`, so a ready runtime sat permanently "degraded" | the fake spoke a richer dialect than the real server |
| `ddf4232b7` | `stop()` 500'd across event loops — the subprocess handle belongs to the loop that spawned it | never exercised cross-loop |
| `ce36b9969` | the 5s **per-probe** timeout doubled as the whole **cold-start** deadline, so every on-demand start failed its triggering run and succeeded on manual retry | no test loaded a real 8B model |
| `49bdad4eb` | the cleanup prompt made the local model emit markdown hard breaks on every line | no test read the output as text |

The pattern is one thing said five ways: **a fake that is more generous than
the real server turns an integration bug into a green build.** The fakes now
match real granularity.

---

## 9 · What is still broken, as tickets

| Ticket | Size | Detail |
|---|---|---|
| **oMLX sidecar exits mid-run** | large | `local inference process exited 3` after a few vision calls; blocks the entire local-vision story |
| **Fresh-install defaults cannot run a third of the presets** | medium | With pure Apple defaults, Auto-Detect, Describe, Extract Table, Detect Regions (VLM), the three AI Converts and Group Same Documents all refuse — *correctly and with excellent messages*, but the out-of-box experience still fails. Options: route classify/describe-class steps to Apple Intelligence where it can serve, or surface the preflight verdict in the workflow list **before** run time. |
| **`error_kind` is embedded in error STRINGS** | small | `[kind]` prefixes and classified wrappers, not a structured field on the thread status. A machine-tracked matrix cannot record it as a column. |
| **`builder` lets a plain edge target a `_process` node** | medium | The shipped-preset guard keeps the presets out of the trap; user-authored workflows can still draw the mixed fan-out/chain shape. The builder should reject or join it. |
| **CLI accepts a short doc id and then fails obscurely** | small | `workflow run` with `b0dd8e2f` → "0 processable files … ids=['b0dd8e2f']". Either resolve short ids like `docs get` does, or say "pass the full document id". |
| **Node-cache rows poisoned before the skip-if-done fix persist** | small | The fix stops new poisoning; it does not scrub existing rows (scratch libraries only, as far as is known). |
| **`output_language: auto` on sparse claim context** | small | ~50 chars of entity context produced a **Spanish** narrative for an English cover page. Resolve language from the document's metadata, not the prompt text. |
| **Apple Intelligence transient `GenerationError`** | small | FoundationModels code -1 / ModelManagerError 1013 failed one run and passed identical inputs 30 min later. A retry ladder if it recurs. |
| **`perf_baseline.json` keys stale test ids** | small | The Convert rename left `…[Convert to Markdown]` entries behind. |

---

## Sources

Every verdict in the matrix traces to one of these, all in
`agent-work/design/`:

- `workflow-exercise-report.md` — the overnight four-config preset sweep (8 fixes)
- `text-workflows-report.md` — transcribe / clean up / translate / describe (5 fixes)
- `extract-organize-report.md` — extract / organize / books, and the Extract-Data merge (4 fixes)
- `convert-export-tools-report.md` — the Convert re-scope, the export matrix, the 126-tool sweep (2 fixes)
- `catalogue-chain-report.md` — Catalogue as the 1–6 chain, three providers (2 fixes)
- `vision-region-experiments.md` — Apple Vision regions, the text→boxes backfill (7 changes)
- Raw rows: `agent-work/design/workflow-exercise/*.json`
- MLX harness + sweep: `/tmp/mlx-lane/` (scratch, deliberately not in the repo)

Static analysis in this report (preset/tool inventories, the prompt-similarity
diffs, the historical-name audit, the `documents`-port sweep, the text-cleanup
tool comparison) was produced directly against this worktree.
