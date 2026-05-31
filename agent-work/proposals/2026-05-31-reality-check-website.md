# Reality Check — Website
**Date:** 2026-05-31
**Auditor:** claude-sonnet-4-6
**Scope:** Open issues in "Website" GitHub milestone (tubb.ca/fichero)
**Method:** grep + Read — site lives at site/src/apps/fichero/

---

## Summary

| Metric | Count |
|---|---|
| Open issues checked | 2 |
| DONE (safe to close now) | 1 |
| PARTIAL | 1 |
| OPEN (needs work) | 0 |

**Safe to close now:** #662

---

## Issue-by-Issue Classification

### #662 — Update tubb.ca/fichero with release notes, download link, and feature overview for 0.0.2
**Classification: DONE — safe to close**

**Evidence (site/src/apps/fichero/index.md):**

All three acceptance criteria are met:

1. **`index.md` updated with feature overview and system requirements** — the file contains a full "What is Fichero?" section, "What It Does" (Document Library, Semantic Search, Workflows), "Who It's For", "System Requirements" (macOS 15.0+, Apple Silicon). Detailed and current.

2. **Download button pointing at release** — line 77: `<a href="https://github.com/dtubb/fichero-releases/releases/latest" class="btn">Download Fichero 2026.04.29 Alpha</a>`. A download button exists with a `#download` anchor above it.

3. **Release notes section** — lines 85+: full "Releases" section with `### 2026.04.29 — Alpha` covering new features (KG layer, four workflows, per-page extraction), improvements, security fix, "What's in this release" + "Not yet in this release" sub-sections.

**Caveat on appcast.xml:** The issue acceptance criteria also include "appcast.xml added to site/src/apps/fichero/ for Sparkle auto-update feed." No `appcast.xml` was found anywhere in `site/`. However, this is tightly coupled to #296 (Sparkle release hosting pipeline), which is a separate open issue. The core deliverable of #662 (feature overview + download + release notes) is complete.

**Action:** Close #662. Note in closing comment that appcast.xml is tracked by #296.

---

### #665 — Write dev blog post: building Fichero — 3 years of 100% AI-assisted coding
**Classification: OPEN**

**Evidence:**
- `site/src/apps/fichero/` contains only: `css/`, `faq.md`, `images/`, `index.md`. No `blog/` directory. No blog post file exists anywhere in `site/src/`.
- The issue asks for a 800-1500 word post published at `site/src/apps/fichero/blog/` (or similar), covering origin story, process evolution, autonomous loop workflow, and honest reflections.
- The issue explicitly states "Daniel reviews and rewrites before publishing — Claude drafts, Daniel polishes" — so Claude can draft but Daniel must approve before publishing.

**Action:** Leave open. No draft exists. This is a writing task (draft blog post) that Claude can do autonomously, then hand off to Daniel for review. Low-effort (~2-hour) writing task, not a coding task.

---

## Disposition Table

| # | Title | Classification | Action |
|---|---|---|---|
| 662 | Update tubb.ca with release notes + download | DONE | **Close now** (appcast.xml left to #296) |
| 665 | Dev blog post: 3 years AI-assisted coding | OPEN | Leave open; no draft exists; needs Daniel review before publish |

## Safe to close now
- **#662** — feature overview, download link, and release notes are all present in `site/src/apps/fichero/index.md`.

## Needs:human
- **#665** — Daniel reviews and rewrites the draft before publishing.
