# Extract / Extract Data / Organize / Books — exercise, fixes, and the family merge (2026-09-03)

Lane report for the EXTRACT, EXTRACT DATA, ORGANIZE and BOOKS workflow
families. Method as in `workflow-exercise-report.md`: real runs through the
CLI/HTTP API against the Marshall scratch library
(`~/code/fichero-worktrees/.workflow-exercise/`, engine on `:8767` running
this worktree's code), three model configurations, ≤6 cloud page-calls per
model per family. Every silent no-op below was root-caused, fixed with a
regression test, committed, and re-verified live on the restarted engine.

## Matrix — preset × model

Legend: ✓ ran end-to-end, artifact/nodes verified · ✗→✓ live failure,
root-caused + fixed tonight, re-verified green · ⊘ correct capability
refusal on Apple factory defaults (wiring pass) · n/a no model involved.

| Preset (family) | apple defaults | openrouter gemini-3.1-flash-lite | openrouter claude-sonnet-4.5 |
|---|---|---|---|
| Diary Entries (Extract) | ✓ (overnight run) | ✓ 3 dated child entries, per-day content + date attrs | ✓ 1 entry on the half page (correct) |
| Extract Table (Extract, ex-/Convert) | ⊘ preflight | ✓ (overnight: real CSV of the tally table) | — |
| Extract Geo (Extract, ex-/Convert) | fixed by 5739e05d8 (documents wiring) | — | — |
| Accounts → Spreadsheet (CSV) (Extract) | ⊘ preflight | ✓ real CSV rows from the 1922 tally page; graceful header-only CSV on a page with no accounts | — |
| Regesto (Archival Abstract) | ✗→⊘ (was mid-run failure; now preflight) | ✓ proper regesto fields | ✓ markdown regesto |
| Modernización (Spanish) | ✗→⊘ (same) | ✗→✓ (was a silent 70ms no-op; real artifact now) | — |
| Translate to English (Historical) | ✗→⊘ (same) | ✗→✓ (same class) | — |
| Group Same Documents (Organize) | ⊘ preflight | ✗→✓ two byte-identical covers clustered + MOVED into "Same Document" folder via audited actions; distinct page untouched | ✓ idempotent re-run |
| Split Chapters (Books) | ✓ n/a model | n/a | n/a |

Books detail: a 6-page book PDF with a TOC split into 3 chapter **group
child nodes** with correct titles, `start_page`/`end_page` and the pages'
concatenated text as `page_content` (basis `outline`); the same book without
a TOC split identically via the heading heuristic (basis `heading`); re-run
replaces rather than duplicates (3 chapters after a second run). The
overnight "No PDF source" row was simply the JPEG sample — with a real PDF
the preset works. Note: `workflow run` needs the FULL 32-hex doc id; an
8-char prefix fails with the (good) "0 of 1 ids" message.

## Defects found live and FIXED (each with a regression test)

1. **`ad2e61b29` — similarity blew up on percentage-scale cluster scores.**
   The default similarity prompt scores aspects 0–100, so gemini flash-lite
   echoed that scale into `same_document_clusters.similarity_score` (100);
   the `le=1.0` pydantic bound failed the whole Group Same Documents run
   after ~9 min of retries. Scores in (1, 100] now normalise to fractions,
   and the prompt states the 0–1 contract explicitly. Regression test runs
   the shipped preset end-to-end with percentage scores.

2. **`d43a1d14b` — prompt-shaped tools returned another preset's artifact
   as their own result (the worst silent no-op of the night).** The
   skip-if-done seam matches `(document, artifact_type, provider, model)` —
   never the prompt. All three paleo presets share `analyze`/`analysis`, so
   after one Regesto run, Modernización and Translate to English
   "completed" in ~70ms returning the Regesto text verbatim and saving
   nothing (cache forensics: their node-cache rows contain the Regesto
   output byte-for-byte). Same collision class pairs Extract Table with
   Accounts → Spreadsheet on `table`. Both tools now opt out of
   skip-if-done; identical re-runs still dedupe via the node cache, whose
   key includes the prompt.

3. **`dfb8fa14d` — analyze refused apple-vision mid-run instead of at
   preflight.** The 2026-09-01 sweep gave every prompt-parsing vision tool
   `requires_generative_model` but missed analyze, so the paleo presets
   passed preflight on factory defaults and died mid-run with a systemic
   error. Declared; keyless fresh-install test now expects the three paleo
   presets in the refuse-at-preflight class.

## THE MERGE — implemented (`a783c9618`)

Daniel: "Extract and Extract Data should be one, no?" Yes — shipped:

- **Before**: /Extract = Diary Entries alone. /Extract Data = Accounts →
  Spreadsheet + three paleography *derivations* (Regesto, Modernización,
  Translate Historical). Extract Table and Extract Geo — the only presets
  literally NAMED "Extract" — hid in /Convert.
- **After**: one **/Extract** family (icon `tablecells`): Diary Entries,
  Extract Table, Extract Geo, Accounts → Spreadsheet (CSV), Regesto,
  Modernización, Translate to English (Historical). /Convert keeps the
  three AI format converters (HTML/Markdown/SVG) — cleaner there too.
  /Extract Data is retired from `workflow_folders.json`.
- **Mechanics**: each moved preset bumps `preset_version` (manifest
  refreshed for exactly those six), so existing libraries heal on next
  open — verified live: after reseed the engine serves all seven under
  /Extract and the folder taxonomy without /Extract Data. Swift only ever
  had "Extract Data" in its served-order FALLBACK list — harmless for a
  folder that no longer exists (left alone; flag for a later Swift sweep).
  Docs regenerated for the affected pages only.
- **Pinned** by `test_extract_family_merge.py`.

**One ruling still Daniel's**: the three paleography derivations are
*readings* (modern orthography, archival abstract, historical translation),
not extraction. They sit in /Extract today so nothing is orphaned, but
their natural home is the paleography program (memory:
paleography-workflow-redesign). If a /Paleography family is approved, the
move is three `folder_path` lines + version bumps.

## Flagged, not fixed (other lanes / shared plumbing)

- `compact_output_for_state` crashed with "Object of type datetime is not
  JSON serializable" during a sibling lane's 'Translate the Reviewed
  Transcription' run — a tool returned un-serialised datetimes into state.
- CLI `--json` output for `artifacts list` can contain raw control chars
  (invalid JSON — needed `strict=False` to parse). CLI lane.
- Cluster folders are named by the model's cluster numbering ("Same
  Document 2" when the dupes are cluster 2) — cosmetic.
- Node-cache rows poisoned by defect #2 before tonight persist until the
  source file's mtime changes or the cache is cleared; the fix stops new
  poisoning but does not scrub old rows (scratch-lib only, as far as known).

## Commits (this lane, tonight)

- `ad2e61b29` fix(organize): similarity accepts percentage-scale cluster scores instead of failing the run
- `d43a1d14b` fix(extract): prompt-shaped tools stop reusing another preset's artifact as their own result
- `a783c9618` feat(workflows): merge Extract Data into one Extract family
- `dfb8fa14d` fix(extract): analyze refuses recognition-only vision at preflight, not mid-run
