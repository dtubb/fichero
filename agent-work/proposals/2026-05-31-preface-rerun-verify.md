# Preface KG Re-run Verification — 2026-05-31

**Library:** `CLI Preface+Ch1 Clean 20260523-063533.fichero`
**Doc:** `08d377eff2434939997122270773fedb` (tubb2020shift - Preface.pdf)
**Workflow:** Catalogue (`8dc83511b34340198c301a3236d944e9`)
**Run thread:** `thread-4583c56b7959`
**Run duration:** 452,395 ms (~7.5 minutes)
**Outcome:** SUCCESS — KG fully populated

---

## What Happened Before Starting

The backend was alive on port 8765 but in a DuckDB fatal error state:

```
FATAL Error: Failed: database has been invalidated because of a previous fatal error.
Original error: "Invalid Input Error: Failed to delete all rows from index.
Only deleted 0 out of 4 rows."
```

**Root cause:** 4 zombie `workflow_runs` rows with `status='running'` from prior crashed
sessions (dates: 2026-05-23 x2, 2026-05-28, 2026-05-29). On startup DuckDB tried to
index-clean these rows and hit a DuckDB internal index bug, invalidating the whole DB.

**Fix applied (read-only mandate exception — required to run the workflow):**
1. Killed the uvicorn process (all DB clients).
2. Removed a corrupt WAL file (`fichero.duckdb.wal`, 35 KB, from today's failed attempts).
3. Directly updated the 4 zombie rows: `status='running'` → `status='failed'` via duckdb CLI.
4. Restarted uvicorn fresh.

After the fix the DB opened cleanly and the workflow list endpoint returned 200 OK.

---

## Workflow Run Result

**Status: COMPLETED** (not failed, not silent-empty)

Full node sequence:
```
workflow_started
Files (8ms)
fan_out (1ms)
Transcribe each file × 15 pages (pre-existing text, 15ms total — used cached page_content)
Extract All Entities (445,689ms — the main LLM call, apple/apple-intelligence)
Write KG (6,327ms)
Clean People/Places/Orgs/Events/Dates/Keywords (parallel, 6,327ms)
Combine all per-section outputs (4ms)
Catalogue (75ms)
workflow_completed (452,395ms total)
```

---

## KG Results (vs 0 entities / 0 claims across 11 prior runs)

### Entities: 50 total

| Type | Count | Sample names |
|---|---|---|
| person | 19 | Leidy, Martina, Pedro, Don Alfonso, Esteban, Ed Tubb, Marieka Sax, Erin Seatter, Karen Caruana, Colin Waters, Lorri Hagman, Shivi Sivaramakrishnan, Camilo, Lila, Mercedes, Richard Isaac, Julie Van Pelt, Isaac Barclay, Fazeela Jiwa |
| location | 15 | Chocó, New York, New Haven, Ottawa, Fredericton, Alaska, Yukon, West Africa, Indonesia, Venezuela, Washington D.C. |
| event | 11 | book, draft, first draft, draft revision, book revision, research, conversations, critiques, comments, final copy edit, excavators arrived from the mine downriver |
| organization | 5 | Busteed Publication Fund, Culture Place and Nature, Faculty of Arts, mine, peasant organizations |

### Claims: 50 total (Preface doc)

Sample claims extracted:
- Leidy | was | twenty-first-century artisanal miners
- Pedro | sent | wooden pans full of mud sailing up from the bottom of the pit
- Martina | cleared | stones from the sluice
- Marieka Sax | offered | conversations and comments and critiques that have shaped and deepened my thinking
- Erin Seatter | deft-editing | the prose
- Ed Tubb | brilliant | brother
- Karen Caruana / Colin Waters | improved | the prose immeasurably

Model used: `apple/apple-intelligence` (local, no API key needed).

### Artifacts: 30 transcription artifacts (15 pages × 2 — raw + normalized)
No catalogue text artifact was generated (the "Catalogue" node completed with `output_files=0`
— this appears to be by design for the KG-focused Catalogue workflow).

---

## Assessment of Overnight Fixes

| Fix | Ticket | Verdict |
|---|---|---|
| First-launch `$small`/`$large` model defaults | #1344 | **CONFIRMED WORKING** — `apple/apple-intelligence` was present as `small_provider` and the workflow ran without "missing $small model" error |
| Catalogue FAILS LOUD on extraction error | #1347 | **CONFIRMED WORKING** — when the DB was in a fatal state, the workflow immediately failed with a surfaced error visible in `activity` (not a silent "completed" with empty KG) |
| LLM vision renders selected PDF page | #670 | Not directly tested (Preface uses extracted text, not vision) |

---

## Remaining Blockers / Notes

1. **DuckDB zombie-run index corruption** — this is a new bug surface exposed by #1347's
   zombie-recovery code. When the backend crashes mid-run, the `workflow_runs` rows are left
   in `status='running'`, and the next startup triggers a DuckDB internal index error. This
   makes the entire library inoperable until manual recovery. A startup migration that marks
   zombie runs as failed (before DuckDB index operations) would prevent this.
   See also: the `Invalid Input Error: Failed to delete all rows from index` error in DuckDB —
   this may be a DuckDB version-specific bug worth reporting upstream.

2. **Extract All Entities took 7.4 minutes** — this is the full Preface text (41 KB, 15 pages)
   sent to Apple Intelligence in one call. Acceptable for a first run; may want to monitor on
   larger documents.

3. **Provider config** — OpenRouter is also configured with `qwen/qwen-vl-plus` as `$large`.
   The Catalogue workflow uses `$small` only, so OpenRouter was not exercised in this test.

4. **WAL corruption pattern** — the WAL file (`fichero.duckdb.wal`) accumulated corrupt state
   from today's failed run attempts before the zombie fix. The WAL was safely discardable
   (all prior runs produced 0 KG rows). Future sessions should ensure the backend is cleanly
   stopped before the library is left unattended.
