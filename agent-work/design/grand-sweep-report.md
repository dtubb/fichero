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

*Recommendation:* **RETIRE the cleanup half; JUDGE the extract half on
usefulness.** Daniel's correction to this lane's first draft is the right one:
*unshipped is fine — the questions are does it WORK, and is it USEFUL for
Fichero.* Reference count is evidence, not a verdict. Applying that:

- The twelve **`<type>_page_cleanup` / `<type>_folder_cleanup`** tools are
  machinery, not capabilities. They deduplicated candidate lists *within* the
  monolith's own pipeline; stage 4 (Merge / Dedup) now does that job against
  persisted KG rows, which is strictly better because it is re-runnable and
  reviewable. **Superseded — retire.**
- The **`<type>_extract` section tools** are a different question, and the
  interesting one. "Pull every direct quote out of this page" is a real
  archival-research act, independent of whether a catalogue is being built.
  The open design question — Daniel's — is whether they should attach to the
  **diary-entry structure** the Catalogue chain produces rather than emitting
  flat per-document results. A quote that knows it belongs to *Tuesday 9
  January 1923* is worth considerably more to a historian than a quote that
  knows only which page it was on. **Judge per family; see the usefulness
  table below.** `quotes_extract` and two or three siblings are queued for a
  live Apple/MLX sample run (free) at the all-clear; until then their "works?"
  column is honestly marked untested.
- `citations_extract` stays under review regardless — the catalogue
  restructure recorded citations as a capability that was *dropped*, so it may
  need a home rather than a retirement.

*Sequencing:* verify by direct reference search, never by `find_dead_code` —
its import graph is blind to `@register_tool`.

*Risk:* a user-authored workflow in an existing library could reference a
retired tool. Retirement should leave it resolvable-with-a-message rather than
crashing an old graph.

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

*Recommendation:* **MERGE — and treat this as a correctness exposure, not
tidiness.** The two data-destruction fixes landed this week (prose deletion
`b240664df`, tally-number deletion) went into `text_passes`. `text_reflow` and
`ocr_cleanup` import nothing from it, so **those fixes cannot reach them**.
Today that costs nothing because no preset routes through either tool — but the
palette offers both, so a user-authored workflow can pick up the unhardened
copy of logic we have already had to fix twice. Keep `clean_text` as the one
text-cleanup tool; either retire the other two or reduce them to thin wrappers
over `text_passes` so the next fix lands once. 432 LOC of parallel regex goes
away with them.

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

**SHIPPED tonight (`51f36479f`):** the guardrail —
`test_auto_detect_prompts_match_sources.py` pins each of the four copies to its
source, with a synthetic fixture proving it fires on a one-sided tune. Drift now
fails the gate. The fifth embedded prompt (the paleography review pass) has
*already* diverged from Paleographer Review's first pass and is deliberately
different — it folds three passes into one — so it is not pinned.

**The structural fix, specced not shipped.** Daniel's instinct is right —
*"those should be chained in there, no? or we should be able to embed other
prompts?"* — and there are two ways to do it:

- **(a) A prompt reference in the preset format.** The format already has a
  reference syntax, but only for *data flow*: a node's `inputs` can say
  `"$.nodes.files-source.documents"`. Config values have no equivalent. Adding
  `"prompt_ref": "transcribe_htr.json#transcribe"`, resolved in
  `_load_preset_files()` (the single choke point every loader goes through),
  is about fifteen lines and produces a seeded row byte-identical to today's —
  so no `preset_version` bump and no behaviour change at all. What makes it
  *not* a fifteen-line change is that **four other things read the preset JSON
  raw**: `preset_manifest.py` (hashes the bytes, so the manifest must be
  refreshed), `scripts/generate_capability_reference.py` (would document a
  preset with no prompt), `scripts/verify_workflows.py`, and several tests.
  All four need to resolve refs too, or the reference leaks into the docs.
- **(b) Auto-Detect as a router over the real presets** — Daniel's other
  suggestion, and the better one. The preset already routes by
  `route_map: {"typescript": "transcribe-ts", …}`; if a `sub_workflow` node is
  a legal route target, those four branches become sub-workflow nodes naming
  *Transcribe Typescript*, *Transcribe Manuscript*, *Transcribe HTR* and
  *Transcribe Paleography*, and the prompts stop existing in this file. This is
  exactly the pattern `catalogue.json` v6 uses for its six stages. It is the
  right shape and it removes the duplication at the source rather than policing
  it.

  The honest catch: the HTR and paleography branches currently do more than the
  standalone presets — each runs a reference `search` and a `transcribe_review`
  pass afterwards. Routing to the plain presets would silently drop that
  two-pass review; routing to *Transcribe + Review (Pipeline)* changes which
  review runs. So (b) is a **behaviour change that needs live verification on
  real pages**, which this lane cannot run tonight. Recommended as the next
  preset-lane task, with the guardrail holding the line until it lands (the
  test says in its own docstring to delete itself when the restructure
  arrives).

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

**SHIPPED tonight (`51f36479f`):**
`resources/workflow_meta/preset_name_ledger.json` records every name ever
shipped (70: 52 current + 18 retired) and
`test_preset_names_never_stranded.py` pins it in both directions — every ledger
name must be shipped or retired, and every shipped name must be in the ledger,
so the ledger cannot go stale and start passing by knowing less. A synthetic
fixture proves the guard fires on a rename that forgets to retire. The failure
message names the file to edit and says explicitly *not* to fix it by deleting
the name from the ledger.

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

### R-11 · SPEC: an explicit model choice should flow to every vision step

Daniel: *"when I transcribe but have chosen a fancy model, use that to do
regions too."*

**Current behaviour, precisely** (read from the code, not assumed):

- A chain step's model is a **per-step** property — `provider_override` /
  `model_override` ride on each `ChainStep` through `/api/chains` and are
  applied per step by the runner.
- An **unpinned** step does *not* inherit anything from its neighbours. It
  resolves its own **tier** from what its tool declares it needs (`category`,
  `requires_generative_model`, a workflow's `requires_vision`) and then takes
  the Settings default for that tier — `WorkflowBarModelTier`.
- That is deliberate, and it fixed a real bug on 2026-09-01: previously every
  step inherited the **selection's** tier, so the bar promised "use apple-vision
  to Detect Regions → then use apple-vision to Transcribe → then use
  apple-vision to Accounts→Spreadsheet (CSV) → then use apple-vision to
  Translate", and the last two steps could not possibly work.
- A run-level override **does** reach a Detect Regions node in VLM mode:
  `node_uses_llm()` is config-aware and returns true for
  `detect_regions` with `provider == "vlm"`, precisely so the model picker,
  the runner and `requires_vision` cannot disagree (Daniel, 2026-08-27).
- A run-level override **cannot** reach nodes inside a `sub_workflow`, and the
  engine refuses such a run out loud rather than dropping the override
  silently: *"all of its model work happens inside sub-workflow X, which a
  run-level override does not reach."*

**So the gap Daniel is describing is real and specific:** pin a capable VLM on
the Transcribe step, and an unpinned *Detect Regions (VLM)* step in the same
chain still resolves `$vision_medium` from Settings — usually Apple Vision —
and refuses (see R-4). The user made an explicit choice and it stopped at one
chip.

**Proposed rule:** an explicit user model choice on any step becomes the
default for every **capability-compatible** step in the same run, unless that
step is individually pinned. Precedence: *step pin > run-level explicit choice >
tier default from Settings.* "Capability-compatible" is the load-bearing
qualifier and is what keeps the 2026-09-01 fix intact — a vision choice flows
to vision steps only, never to a text step, which is exactly the failure that
fix removed. Spreading the *selection's* tier was wrong; spreading a
*deliberate* choice within a capability class is right.

**Why this is a spec and not a patch:** it changes run semantics across the
workflow bar, the chain runner and the per-node resolver at once, and its whole
value is in what the user sees before they spend money. The honesty rule holds
either way and already works: the bar names the model **per step**, so an
inherited choice must render as the inherited model on every step it reaches —
if the sentence cannot show it truthfully, the inheritance should not ship.

### R-12 · FIX: a table tool that cannot say "there is no table"

`table_extract` on a table-less manuscript page returned a table of `0,1,2…30`
— it had read the **centimetre ruler** placed beside the document in the scan.
Nothing in the tool guards against a fabricated table.

This is the same family as the silent no-ops fixed this week, but worse in
kind: those returned *nothing* while claiming success; this one returns
*invented data* while claiming success, into an archive whose entire value is
that its contents are attested. A scanning ruler is present in a large share of
archival images, so this is not an exotic input.

**SHIPPED (`9722ccecb`).** Two halves:

- **The prompt now offers a way to say no.** `NO TABLE` is documented as a
  correct and complete answer, and the rules name the furniture that caused
  this — rulers, scale bars, colour charts, folio strips — as belonging to the
  act of scanning rather than to the document. The rules ride with **every**
  prompt including a custom one, because *Accounts → Spreadsheet (CSV)* ships
  its own and is the preset most likely to meet a page of prose. Appending is
  idempotent.
- **The reply is validated before it is saved**, through the same
  `postprocess_text` seam Convert uses to refuse malformed SVG (#4329). An
  empty answer, the sentinel, or a single column of six-or-more consecutive
  integers refuses the save *with its reason* and persists nothing. A folder
  where three pages in ten carry tables now yields three tables and seven
  recorded "no table here", instead of ten tables of which seven are fiction.

The ruler signature is deliberately narrow: Marshall's one-column dredge
tallies are not consecutive and are not caught, nor is a short numbered column,
nor numeric data with a second column. 14 tests, all four refusals and all
four keeps pinned.

Worth recording how this was found: **the free local model caught it.** A 3B
model running on Daniel's own machine, costing nothing, surfaced the most
serious defect in a sweep that also spent real money on two cloud providers.
That is the argument for keeping the local column in the matrix even while it
is the slowest one.

### The KEEP / MERGE / RETIRE table

Judged on Daniel's axis: **(a) does it work when exercised, (b) is it genuinely
useful for an archival-research app, (c) is it superseded?** Reference count is
evidence in the last column, never the verdict.

| Tool / group | Works? | Useful for Fichero? | Verdict |
|---|---|---|---|
| `clean_text` (+ `text_passes`) | yes, hardened twice this week | yes — the one text cleanup | **KEEP** |
| `text_reflow`, `ocr_cleanup` | yes, non-destructive on real pages | duplicates `clean_text`'s toggles | **MERGE** — and the hardening cannot reach them (R-3) |
| `handwriting` | **no** — ALL-CAPS, lines repeated verbatim, violates its own no-repeat rule | superseded by `transcribe` + an HTR prompt, which is better on the same page | **RETIRE** (or merge into `transcribe`) |
| `table_extract` | works — fabrication now refused (R-12) | yes, tables are real archival data | **KEEP** — guarded `9722ccecb` |
| 12 `<type>_page_cleanup` / `<type>_folder_cleanup` | untested since the restructure | machinery of a retired pipeline; stage 4 does it better and re-runnably | **RETIRE** |
| `<type>_extract` section family (quotes, people, dates, events, keywords, …) | **untested — queued for a free live sample** | plausibly yes *as standalone acts*; much more so if wired to diary entries | **HOLD — decide after the sample run** (R-1) |
| `citations_extract` | untested | citations were dropped by the restructure and never rehomed | **HOLD — may need a home, not a retirement** |
| 4 language paleography presets | yes, all green on two providers | yes, but they are one preset plus an enum | **MERGE (ruling)** — or keep for discoverability |
| 3 paleo derivations in /Extract | yes | yes — but they are *readings*, not extraction | **MOVE (ruling)** to a /Paleography family |
| Auto-Detect's 4 embedded prompts | n/a | n/a | **FIXED tonight** (guarded); structural fix specced (R-6) |
| 16 palette stubs | **no — not executable** | `if`/`loop`/`filter`/`merge` are a visible promise the engine does not keep | **DECIDE** — implement the 5 logic nodes or take them out of the palette |
| 5 agent tools, 3 research tools, audio/video | untested | unclear — no archival use case has been articulated | **KEEP, PROVE** — one exercise pass, then judge |
| 4 unpresented image ops (denoise, deskew, binarize, auto-crop) | yes | yes — scan hygiene is daily work here | **KEEP + SURFACE** — one "Clean Up Scans" preset |
| `tested` field on ToolDef | true for 6 of 142 | a flag nobody maintains teaches readers to ignore it | **POPULATE or DELETE** (R-9) |
| `/api/chains/presets/paleography` | untested | rebuilds an approach Daniel retired | **RETIRE** (R-2) |
| Preset name stranding | n/a | n/a | **FIXED tonight** — ledger + guard (R-8) |


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

The local column moved twice in two days, and an earlier draft of this report
got its verdict wrong. Correcting that on the record.

- **2026-09-02:** local MLX vision was *impossible*, and had never been
  possible. Every model in `MANAGED_MLX_MODELS` is a vision/OCR VLM and every
  one was served by `mlx_lm server`, whose `process_message_content` rejects
  any non-text content part. Verified live rather than inferred: Qwen3-VL-8B
  answered a text prompt in 56s and returned
  `404 {"error": "Only 'text' content type is supported."}` for the very image
  the model exists to read. Local *text* workflows (Clean Up Text LLM,
  Translate, Diary Entries, NER) worked fine throughout.
- **2026-09-03/04:** the MLX provider lane fixed four separate breaks — the
  runtime now provisions **mlx-vlm** and vision models launch `mlx_vlm.server`;
  installed models are listed from the store rather than from a sidecar that
  only starts on demand for a run; managed models go over the wire as the
  resolved **snapshot path** instead of our catalog id (which sent the sidecar
  to Hugging Face for a model already loaded in the process being asked); and
  the cold-start budget went to 300s, because `mlx_vlm.server` preloads the
  model *before* uvicorn binds, so the port refuses connections for the entire
  load and a probe cannot tell that from nothing being there.
- **The `local inference process exited 3` cascade I recorded in an earlier
  draft was those breaks, not a crash under memory pressure.** After the fixes,
  a clean sweep on Qwen2.5-VL-3B produced **ten greens and one honest refusal**.

**Verdict for the MLX column: LOCAL VISION WORKS.** On real 17th-century
colonial Spanish secretary hand, Qwen2.5-VL-3B gives a genuine diplomatic
transcription; `classify_script` returns `htr` at 0.9 confidence with
"16th–19th century", which is both correct and well calibrated. The remaining
MLX caveats are speed (236s for a page, against ~27s for cloud Sonnet) and
memory headroom (the 8B profile swap-deaths a 16 GB M1), not capability.

Two tool-level defects the local sweep exposed — worth having, because a free
local model is the cheapest way to run this kind of sweep at all:

- **`handwriting` produced ALL-CAPS output with verbatim repeated lines**,
  worse than `transcribe` on the same page, and violating its own prompt's
  no-repeat rule. See the usefulness table: this tool is superseded.
- **`table_extract` FABRICATED a table** (`0,1,2…30`) on a page that has none,
  by reading the **centimetre ruler** lying in the scan margin. The perception
  is understandable; the output is invention, and **nothing guards it**. A
  table tool that cannot say "there is no table here" will quietly manufacture
  data in an archive. That is the most serious single finding of the sweep.

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
| ~~**`table_extract` fabricates tables**~~ | — | **FIXED `9722ccecb`** — "no table" is now a first-class answer and the save is refused with a reason (R-12). |
| **`handwriting` is worse than `transcribe`** | small | ALL-CAPS with verbatim repeated lines on a page `transcribe` reads correctly, violating its own no-repeat rule. Retire or merge (see the usefulness table). |
| **MLX speed and memory headroom** | medium | Local vision now *works* (10 greens on Qwen2.5-VL-3B). What it is not is fast — 236s a page against ~27s for cloud Sonnet — and the 8B profile swap-deaths a 16 GB M1. Capability is no longer the blocker; throughput is. |
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
