# Milestone Audit: Exporter — 2026-05-30

## Summary

| Action | Count |
|---|---|
| Total issues in milestone (all states) | 14 |
| Open issues | 6 |
| Closed issues | 8 |
| REOPEN candidates | 2 |
| REMILESTONE (wrong milestone) | 3 |
| RELABEL (missing/wrong labels) | 8 |
| Missing PDF-format backend issue (new) | 1 |

---

## A. REMILESTONE — Wrong milestone (closed, completed)

These three closed issues were filed under Exporter but have nothing to do with document export formats. They concern engine startup diagnostics and release configuration. They belong under **Mac App Shell** (milestone #62) or **Infrastructure** (milestone #11).

```bash
# #759 — Engine bundle path logging (diagnostic, not export)
gh issue edit 759 --repo dtubb/fichero --milestone "Mac App Shell"

# #757 — Release build: embedded engine doesn't spawn
gh issue edit 757 --repo dtubb/fichero --milestone "Mac App Shell"

# #278 — Sparkle updater release config for 0.0.1
gh issue edit 278 --repo dtubb/fichero --milestone "Mac App Shell"
```

Rationale: #759, #757, and #278 are all about the app's release/startup pipeline (embedded engine spawn, Sparkle updater, bundle path logging). None relate to export formats. Mac App Shell is the correct home.

---

## B. REOPEN — Closed but idea is still good / untracked

### #475 — Export: static HTML website (closed NOT_PLANNED)
```bash
gh issue reopen 475 --repo dtubb/fichero
gh issue edit 475 --repo dtubb/fichero --milestone "Exporter"
```
Rationale: Closed NOT_PLANNED, but the static HTML export is explicitly named in the Exporter milestone description ("self-contained static HTML site with client-side search") and is a dependency for the Netlify deploy (#476). The work was never done as a standalone backend format route — #1334/#1336 implemented a higher-level 11ty site exporter, which is different from the simple per-document HTML format option (`format: html`) in the shared export router (#470). This format slot is still an open gap. Reopen as the backend format handler that feeds the 11ty layer.

### #472 — Export: Markdown folder (closed COMPLETED)
No reopen needed — this one is legitimately completed per its close reason. Keeping closed.

---

## C. RELABEL — Missing or incorrect labels

All four core backend format issues (#470–#474, #476) and the two gate issues (#505–#508) lack `priority:` and `tier:` labels. The Release Gate issues also carry `status:ready-for-test` which is incorrect — they are future roadmap planning gates that haven't been built, not merged PRs awaiting QA.

```bash
# Export infrastructure router — add priority + tier
gh issue edit 470 --repo dtubb/fichero \
  --add-label "type:task,backend,priority:P1,tier:medium"

# Export: JSON format
gh issue edit 471 --repo dtubb/fichero \
  --add-label "type:task,backend,priority:P2,tier:medium"

# Export: Word (.docx)
gh issue edit 473 --repo dtubb/fichero \
  --add-label "type:task,backend,priority:P2,tier:medium"

# Export: Excel (.xlsx)
gh issue edit 474 --repo dtubb/fichero \
  --add-label "type:task,backend,priority:P2,tier:medium"

# Export: Netlify deploy — backend + client:swiftui (OAuth flow touches both)
gh issue edit 476 --repo dtubb/fichero \
  --add-label "type:task,backend,priority:P3,tier:frontier"

# Release Gate 0.4.0 — remove wrong status:ready-for-test, add roadmap context
gh issue edit 505 --repo dtubb/fichero \
  --remove-label "status:ready-for-test" \
  --add-label "type:task,priority:P2"

# Release Gate 0.4.1
gh issue edit 506 --repo dtubb/fichero \
  --remove-label "status:ready-for-test" \
  --add-label "type:task,priority:P2"

# Release Gate 0.4.2
gh issue edit 507 --repo dtubb/fichero \
  --remove-label "status:ready-for-test" \
  --add-label "type:task,priority:P2"

# Release Gate 0.4.3
gh issue edit 508 --repo dtubb/fichero \
  --remove-label "status:ready-for-test" \
  --add-label "type:task,priority:P2"

# #1334 and #1336 (static site exporter, closed COMPLETED) — missing all labels
gh issue edit 1334 --repo dtubb/fichero \
  --add-label "type:task,backend,client:html,priority:P2,tier:frontier"

gh issue edit 1336 --repo dtubb/fichero \
  --add-label "type:task,backend,client:html,priority:P2,tier:frontier"
```

Note on `client:html`: Issues #1334, #1336, and the static HTML format issues (#475 if reopened) should carry `client:html` — this label exists in the repo and is specifically defined as "Exporter static site + document_view.html". None of the Exporter issues currently carry it.

---

## D. NEW MILESTONE PROPOSAL — None required

All Exporter issues belong to the Exporter milestone. No cross-milestone contamination was found in the reverse direction (no Website issues incorrectly filed here).

---

## E. MISSING ISSUE — PDF export backend format

The Exporter milestone has a complete sibling issue for each format — JSON (#471), Word (#473), Markdown (#472, done), Excel (#474), HTML (#475) — but there is **no dedicated backend issue for PDF export**. The Release Gate #506 mentions "Word + PDF" together, but `python-docx` (Word) and a PDF renderer (WeasyPrint/ReportLab/wkhtmltopdf) are distinct libraries with different implementation paths. Propose filing:

```bash
gh issue create --repo dtubb/fichero \
  --milestone "Exporter" \
  --title "Export: PDF format (WeasyPrint or ReportLab — images + transcription)" \
  --label "type:task,backend,priority:P2,tier:medium" \
  --body "## Goal
Export a document to PDF. Images (edit chain applied) and transcription in a clean typeset layout.

## Implementation options
- WeasyPrint (HTML→PDF, easiest to style with CSS, pure Python)
- ReportLab (direct PDF, more control, heavier)

## Format option: \`pdf\`
Depends on #470.

## Note
PDF generation is separate from Word (#473) — different library, different layout concerns. Split from Release Gate #506 for independent implementation."
```

---

## F. EXPORTER vs. WEBSITE BOUNDARY CHECK

The `Website` milestone (milestone #66) contains `tubb.ca` public site work (#662, #661, #665). No Website issues were incorrectly filed in Exporter. The boundary is clean. The `client:html` label correctly distinguishes Exporter's static site output from the Website milestone's public tubb.ca pages.

---

## Closed issues reviewed (no action needed)

| # | Title | Verdict |
|---|---|---|
| #1336 | Static site exporter: continuous/incremental updates | Legitimately done. Add labels only (see C). |
| #1334 | Static site exporter (11ty) | Legitimately done. Add labels only (see C). |
| #472 | Export: Markdown folder | Legitimately done. No action. |
| #659 | Build, sign, notarize DMG 0.0.2 | Closed NOT_PLANNED. Belongs in Mac App Shell, not Exporter. Remilestone: `gh issue edit 659 --repo dtubb/fichero --milestone "Mac App Shell"` |

```bash
# #659 — DMG build/sign/notarize, not an export format concern
gh issue edit 659 --repo dtubb/fichero --milestone "Mac App Shell"
```
