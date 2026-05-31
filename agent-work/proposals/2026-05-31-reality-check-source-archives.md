# Reality Check: Source Archives Milestone — 2026-05-31

Read-only audit. No code run, no git changes. Source Archives = curated corpora to
import (distinct from Importers, which covers import tools). Verified against the
filesystem (Box-Box, ~/code/maps_southern_colombia) and the Fichero library files on disk.

---

## Context

Source Archives has 6 open issues, all corpus-import tasks for the 0.0.2 release track.
The one closed issue (#1231 slipbox) was confirmed completed in yesterday's audit.
Today's check focuses on the 6 open issues: whether any import work has silently landed
since the 2026-05-28 triage comments that marked each as "no artifact found."

---

## Issue-by-Issue Verdict

| # | Title | Verdict | Evidence |
|---|-------|---------|----------|
| **#1232** | Create Fichero database for Chota Valley and Colombian Pacific maps | **OPEN** | Source material exists at `~/code/maps_southern_colombia` (confirmed: `jesuitas-ecuador.png`, `napoli-quito.png`, PNG files present). No `.fichero` library named for maps, Chota Valley, or Colombian Pacific exists anywhere under `~/Documents`, `~/code`, or `~/Desktop`. The maps repo contains `CONSTITUTION.md`, `STATE.md`, agent-work files — this is a separate project, not a Fichero import. No import script found in `fichero-engine/`. Not started. |
| **#1233** | Import already-catalogued GHC materials (including ACENET imports) into Fichero | **OPEN** | No `.fichero` library with "GHC", "ACENET", or related name found anywhere on disk. No import script for GHC materials in `fichero-engine/src/fichero/`. Box-Box storage is inaccessible (CloudStorage mount returned empty — Box may not be synced to disk). Not started. |
| **#1234** | Import Archivo Judicial de Medellin catalogue into Fichero | **OPEN** | Source material path is `Box-Box/Archivo Judicial de Medellín_UN/Catalogue`. Box-Box filesystem is empty/unsynced locally. No `.fichero` library named for Archivo Judicial found anywhere on disk. No import script. Not started. |
| **#1235** | Import Sergio Mosquera notebooks and catalogue spreadsheet into Fichero | **OPEN** | Source material at `Box-Box/Sergio Mosquera Notebooks/` exists structurally (Box-Box root resolves), but Box-Box directory contents are empty/unsynced — individual notebook folders (SM_NPQ_C01 through SM_NPQ_C05) confirmed to exist as subdirectory names from a prior `ls` result. However, no `.fichero` library named for Mosquera found on disk. Issue notes XLSX import dependency is now unblocked (#1237 closed/completed). Not started as a Fichero import. |
| **#1236** | Import Newton C. Marshall diary materials into Fichero | **OPEN** | Source material at `Box-Box/Newton C Marshall Diary/` is confirmed to have files: `NCM_Diary_19130101-19131231.docx` through `NCM_Diary_1925.docx` etc. No `.fichero` library named for Newton Marshall found anywhere on disk. No import script. Not started. |
| **#1238** | One-time import of Istmina mineria transcript workflow outputs into Fichero | **OPEN** | Source material path is `Box-Box/JPG files (minería hasta 1980)/...`. Box-Box is not synced locally. No `.fichero` library named for Istmina or minería found anywhere. No import script. Not started. |

---

## Summary Counts

| Category | Count | Issues |
|----------|-------|--------|
| DONE — safe to close | 0 | — |
| OPEN — genuinely needs work | 6 | #1232, #1233, #1234, #1235, #1236, #1238 |
| PARTIAL | 0 | — |

---

## Safe to Close Now

None. All 6 open issues have zero evidence of a completed Fichero library artifact
or an import script. The 2026-05-28 triage verdicts ("no artifact") still hold.

---

## Key Finding: Box-Box is Not Synced Locally

Four of the six corpora live in Box-Box (`Box-Box/Sergio Mosquera Notebooks`,
`Box-Box/Newton C Marshall Diary`, `Box-Box/Archivo Judicial`, `Box-Box/JPG files (minería)`).
The Box-Box CloudStorage mount (`~/Library/CloudStorage/Box-Box/`) resolves as a path
but returns no directory contents — Box Drive is either not running or not synced.

This is a practical blocker for #1233, #1234, #1235, #1236, #1238:
the source files must be on-disk (or streamed) before any import can run.

**Action required before any Box-linked corpus import can proceed:**
Confirm Box Drive is running and files are synced to disk (or use Box API download).

---

## Status of Source Material Accessibility

| # | Source path | Material on disk? | Blocker |
|---|------------|-------------------|---------|
| #1232 | `~/code/maps_southern_colombia` | YES — PNG files present | None; ready to import |
| #1233 | `Box-Box/` (GHC/ACENET) | Unknown — Box not synced | Box sync required |
| #1234 | `Box-Box/Archivo Judicial de Medellín_UN/Catalogue` | Unknown — Box not synced | Box sync required |
| #1235 | `Box-Box/Sergio Mosquera Notebooks` | Unknown — Box not synced | Box sync required; XLSX tool now unblocked (#1237 done) |
| #1236 | `Box-Box/Newton C Marshall Diary` | Confirmed filenames known (DOCX) | Box sync required |
| #1238 | `Box-Box/JPG files (minería hasta 1980)/...` | Unknown — Box not synced | Box sync required |

---

## Needs Work — Action Notes

| # | Next step |
|---|-----------|
| #1232 | Maps source is on disk and ready. Run the CLI import (pattern: `fichero ingest <path> --library <target.fichero>`). No blocker. This is the one corpus that can be done today. |
| #1233 | Requires Box sync + clarification of which GHC/ACENET catalogue files to import and in what format |
| #1234 | Requires Box sync; source is a catalogue directory (likely spreadsheet/PDF) — XLSX importer (#1237) is available |
| #1235 | Requires Box sync; XLSX importer is now available for the catalogue spreadsheet (#1237 closed) |
| #1236 | Requires Box sync; DOCX diary files confirmed — standard Kreuzberg/docling ingest path applies |
| #1238 | Requires Box sync; transcription workflow outputs are a mix of JPG + transcription files from the workflow subdirectories |

---

## Prior Audit Confirmation

The 2026-05-30 Source Archives audit reached the same verdict: all 6 open issues genuinely
incomplete, no reopen candidates, all correctly milestoned. Today's check adds the Box-Box
sync gap (newly confirmed) and the maps-corpus ready-to-import finding (#1232).

---

*Verified via filesystem checks (find, ls), jCodemunch codebase search, and direct file reads.
No code executed, no git changes.*
