# docs/ Review — 2026-05-31

Systematic read of all 64 files in `docs/`. Read-only audit; no edits made.

---

## Section A: NEW ISSUES TO FILE

### A1 — PDF Loupe magnifier for PDFs (issue needed)
- **Title:** PDF loupe: magnifier overlay for PDFView (mirror of image loupe)
- **Milestone:** Library & Reading Surface
- **Source:** `docs/superpowers/plans/2026-05-25-loupe-pdf-zoom.md`
- **Rationale:** Fully specced implementation plan with step-by-step code. The image loupe already exists; this extends it to PDFView via an `NSTrackingArea` + `PDFLoupeNSView` overlay. Also fixes image loupe z-order and coordinate drift during zoom. No GitHub issue found for the PDF side of this.

### A2 — Unified verification gate: `verify_all.sh` + `CrossLanguageGateTests`
- **Title:** Implement unified verification gate: `verify_all.sh` + `CrossLanguageGateTests.swift`
- **Milestone:** Developer Experience
- **Source:** `docs/superpowers/specs/2026-05-20-unified-verification-gate-design.md` + matching plan in `docs/archive/superpowers-plans/2026-05-20-unified-verification-gate.md`
- **Rationale:** Fully designed, no GitHub issue found. Closes the "no single gate" gap: one `⌘U` and one terminal command run lint + build + run-smoke + tests for frontend, backend, and CLI. The spec is approved and the implementation plan is checkbox-ready for dispatch.

### A3 — ACENET remote backend: settings UI for remote library path
- **Title:** ACENET remote backend: Settings UI to specify remote library path and token
- **Milestone:** Infrastructure (or Importers)
- **Source:** `docs/remote-backend-acenet.md`
- **Rationale:** The doc describes a fully working SSH-tunnel workflow, but notes that the Swift app has no explicit remote-library path control — you have to copy the token file manually. Issue #1239 covers the feature-level story; this would be the specific sub-issue for "remote library path input in Settings + token management UI." Recommend checking whether #1239 is scoped to cover this already before filing.

### A4 — Ingest: parallel batch processing for independent files
- **Title:** Ingest: parallel file processing for large folder ingestion
- **Milestone:** Importers
- **Source:** `docs/ingest_best_practices.md` §Performance Optimization, `docs/ingest_api.md` §Performance Considerations
- **Rationale:** Both ingest docs explicitly flag "consider parallel processing for independent files" as a future enhancement. Currently `ingest_folder()` is sequential. Batch parallelism would meaningfully speed up large archive imports (the Chota Valley, Mosquera, Marshall diary corpora mentioned in Source Archives milestone). Not currently an open issue.

### A5 — Ingest: fuzzy/content-based deduplication
- **Title:** Ingest: fuzzy deduplication (near-duplicate detection, not just checksum)
- **Milestone:** Importers
- **Source:** `docs/ingest_best_practices.md` §Content-Based Deduplication, `docs/ingest_api.md`
- **Rationale:** The docs explicitly call out "fuzzy matching for similar files" and "content hashing for text files" as a recommendation, but only checksum-exact dedup is currently implemented. Historical archives commonly have near-duplicates (carbon copies, variant scans). Not currently an open issue.

### A6 — Build/release pipeline scripts
- **Title:** Build + release pipeline: `build-release.sh`, `notarize.sh`, `create-github-release.sh`
- **Milestone:** Developer Experience (or Infrastructure)
- **Source:** `docs/superpowers/specs/2026-03-22-build-release-pipeline-design.md`
- **Rationale:** The spec is approved (status: "Approved"). Shell scripts described (`scripts/build-release.sh`, `notarize.sh`, `build-release-dmg.sh`, `create-github-release.sh`, `deploy-site.sh`) are planned but no matching GitHub issue exists. The release process doc (`docs/architecture/release-process.md`) refers to a `/release 0.x.y` skill but the underlying scripts aren't tracked. This is a Developer Experience gap.

### A7 — VALIDATION.md: update stale blocker note
- **Title:** Update `docs/VALIDATION.md`: remove stale "known blocker" note from 2026-02-16
- **Milestone:** Developer Experience
- **Source:** `docs/VALIDATION.md`
- **Rationale:** The doc says "Known current blockers (as of 2026-02-16): SwiftLint reports many existing warnings." Current status is "440+ unit tests passing, 0 regressions, ruff clean" per release notes. The doc's validation status section is now outdated and should be refreshed. Minor but confusing to new contributors. Can be done as a task with no design needed.

---

## Section B: NEW MILESTONE PROPOSALS

### B1 — Security milestone

**Proposed name:** Security

**Scope:** Auth hardening, local token security, remote-backend auth (Tailscale / mTLS), multi-user write permissions, sandboxing audit, keychain management, content scanning for malicious files.

**Feeds from these docs/issues:**
- `docs/remote-backend-acenet.md`: bearer token is a local file `~/.api-key` — no expiry, no rotation UI. The doc says "Keep the backend private. Do not bind it to `0.0.0.0`" and notes the 403-loopback enforcement is the only protection.
- `docs/ingest_best_practices.md` §Security Considerations: "validate file paths, handle symbolic links carefully, implement size limits, scan for malicious content" — none of these are currently tracked issues.
- Issue #969 (open): "Future: more robust engine auth — design for remote (Tailscale / mTLS) and harden the local token path" — already labeled `type:feature`, no milestone assigned.
- Issue #510 (open, milestone: Infrastructure): "[Release Gate] 0.5.1 - Wire: API Security + Auth" — already exists in Infrastructure. If a Security milestone were created, this and #969 would migrate there.
- Issue #1092 (open, roadmap): "Multi-user with write permissions (the engine is single-user today)" — would also belong here.
- `docs/architecture/api/development_standards.md`: no auth-related standards documented (rate limiting, API key rotation, audit logging).

**Recommendation:** A Security milestone is warranted. The current collection of security-relevant work is spread across Infrastructure (which has a very different scope — migrations, IIIF, integrations) and individual `roadmap`-labeled issues with no milestone. Consolidating into Security would give Daniel a clear lane for the "before going open-source" hardening work. Minimum scope for a v1 Security milestone: token rotation UI + Tailscale/mTLS design + keychain audit. Existing issues #510, #969, #1092 would anchor it.

---

## Section C: STALE FILES TO DELETE

### C1 — `docs/archive/BACKEND_BUNDLING_SUMMARY.md`
**Reason:** A one-time "here's what was implemented" summary doc written when `EmbeddedBackendService.swift` was first created. Fully superseded by `docs/BUNDLING_BACKEND.md` (architecture) and `docs/SETUP_BUNDLED_BACKEND.md` (setup guide), both of which are durable and accurate. The summary adds nothing a reader of the two primary docs wouldn't get.

### C2 — `docs/archive/swiftui-api_migration_guide.md`
**Reason:** Migration guide for the old-to-new APIClient migration that referenced "TODO-125" and "TODO-126" as open work. That migration is now complete (the generated `*ServiceGenerated.swift` wrappers are the canonical pattern). The guide references a `~1750 lines of redundant type conversion code` that has since been cleaned up. Keeping it in archive/ is fine but it now actively misleads — its "Critical Architecture Note" is no longer true.

### C3 — `docs/archive/0.0.2-planning/AUTHORITATIVE_ROADMAP_SPEC.md`
**Reason:** A March 2026 planning spec for the 0.0.2→0.1.0 roadmap. All milestone work it describes is now captured in GitHub Issues + Milestones (the `docs/agent-workflow/github-conventions.md` file explicitly says "filesystem planning files are not the source of truth"). Historical only; no durable content that isn't already in GH.

### C4 — `docs/archive/0.0.2-planning/GATE-MAP.md` and `docs/archive/0.0.2-planning/PLAN.md`
**Reason:** 0.0.2 sprint gate map and planning doc. 0.0.2 is done and merged. Pure historical artifact.

### C5 — `docs/archive/agent-workflow/BACKLOG.md`
**Reason:** Pre-GitHub-Issues backlog from February 2026, Phase 0 "constitution & planning" era. Every task in it is either done or represented as a GitHub issue. Has explicit notes about `venv` not existing, `swiftlint` not installed — all long since resolved.

### C6 — `docs/archive/agent-workflow/GATE_MAP.md` (top-level)
**Reason:** Duplicate of (and less complete than) `docs/archive/0.0.2-planning/GATE-MAP.md`. Both are post-0.0.2 detritus.

### C7 — `docs/archive/agent-workflow/PLAN.md` and `docs/archive/0.0.2-planning/PLAN.md`
**Reason:** Two overlapping 0.0.2 planning files. Sprint plans; all work is complete or in GitHub.

### C8 — `docs/archive/agent-workflow/TODO.md`
**Reason:** Pre-GitHub-Issues task list (likely from the same era as BACKLOG.md). The `github-conventions.md` doc explicitly deprecates local task files in favor of GitHub Issues.

### C9 — `docs/archive/agent-workflow/QA_CHECKLIST_0.0.1.md` and `docs/archive/agent-workflow/RELEASE_SURFACE_0.0.1.md`
**Reason:** 0.0.1 release artifacts. Already in archive/; safe to delete now that 0.0.2 is shipped.

### C10 — `docs/archive/agent-workflow/feature-audit-backend.md` and `docs/archive/agent-workflow/feature-audit-frontend.md`
**Reason:** February 2026 static audit reports ("auditor: python-dev, static analysis only"). The codebase has changed substantially since then. No longer actionable; the live GitHub Issues and `find_dead_code` / jcodemunch tooling are the right way to audit now.

### C11 — `docs/archive/agent-workflow/PLAN-0.0.2-knowledge-graph.md`
**Reason:** Sprint plan for KG work that shipped in 0.0.2. Historical only.

### C12 — `docs/archive/superpowers-plans/2026-04-14-backend-review-split.md`
**Reason:** Implementation plan for "fix 11 failing background_tasks tests + split 12 oversized files." Tests are fixed, file splits are done. Checkbox-style plan that's now complete.

### C13 — `docs/archive/superpowers-plans/2026-04-21-activity-view-bugs.md` and `docs/archive/superpowers-plans/2026-04-21-run-workflow-selection.md`
**Reason:** Two one-off bug-fix implementation plans from April 2026. If bugs shipped, these are vestigial; if not, the bugs should be GitHub Issues. Either way the plan files are not durable reference.

### C14 — `docs/archive/superpowers-plans/2026-04-28-typed-entity-storage.md`
**Reason:** Implementation plan for "wire catalogue extractors to write KnowledgeEntity + KnowledgeClaim rows." This shipped (it's core KG architecture now). Plan is complete; no future reader needs to act on it.

### C15 — `docs/archive/superpowers-plans/2026-05-15-module-organization-cleanup.md`
**Reason:** Implementation plan for the module organization cleanup (orphaned route deletions, renames, hermeneutics.py surgery). This committed as an atomic cleanup. Done.

### C16 — `docs/archive/superpowers-plans/2026-05-20-unified-verification-gate.md`
**Reason:** This is the **implementation plan** for the unified verification gate (see Section A2 above for the companion spec). If the gate is built, this plan is vestigial; if not, only the spec is needed for dispatch — the plan is ready-to-execute but duplicates the spec at a lower level. Recommend keeping the spec (`docs/superpowers/specs/2026-05-20-unified-verification-gate-design.md`) and deleting this plan once the gate issues are filed on GitHub.

### C17 — `docs/archive/code-review/2026-02-12/` (all files)
**Reason:** Historical code review notes (Swift architecture + SwiftLint review) from Feb 2026. Patterns noted there are now either fixed or documented in `SWIFTUI_PRINCIPLES.md` and `development_standards.md`. `README.md` in that folder just says "historical review notes." Pure archive; no durable guidance.

### C18 — `docs/qa/workflow-qa-validation-gates.md`
**Reason:** Workflow QA validation gates for the 0.0.1 release (issue #250). Issue #250 would be long closed. If this is a template for future QA gates, the content should move to `docs/agent-workflow/templates/`; as a 0.0.1 artifact it's stale and confusing.

### C19 — `docs/archive/swiftui-inspector_redesign.md`
**Reason:** April 2026 design doc for the Tinderbox-style inspector redesign. This inspired the current `DocumentInspector/` tabbed layout. The design ideas are now implemented; keeping the rationale doc is optional (it's good "why" context) but it belongs in archive (where it already is) or in a GitHub issue comment, not as a doc people might mistake for current guidance.

### C20 — `docs/qa/VIEW_QA_MATRIX.md`
**Reason:** References issues #114, #115, #116 (likely 0.0.1 era issues). If those are closed, this matrix is stale. The `docs/architecture/release-process.md` is the current release-gate protocol. Recommend confirming those issues are closed, then deleting or redirecting to the release process doc.

### C21 — `docs/archive/agent-workflow/feature-flag-design.md`
**Reason:** The feature flag design it describes (`FeatureFlags.swift`, `FICHERO_DEV_MODE`, `/api/feature-flags` endpoint sync) was implemented but the specific design has since evolved (`FICHERO_FEATURE_TIER` replaced the old flag approach for route registration). The doc's code samples reference `FeatureFlags.shared.featureChat` style that conflicts with the current `FeatureManager.swift` pattern. Misleading to any agent trying to understand the current feature gating.

---

## Section D: NOTABLE TOOLS / FRAMEWORKS / VISUALIZATION IDEAS

### D1 — KG visualization: no framework currently specified (gap)
- **Finding:** No doc in `docs/` mentions a specific KG graph-rendering framework for the Mind Palace or KG inspector views. The existing `graph_reasoning.py` uses NetworkX for server-side analysis (centrality, communities), and `pykeen_inference.py` for link prediction — but there's nothing about client-side graph rendering.
- **Candidates worth evaluating** (not mentioned in docs, worth researching):
  - **Swift Charts** (Apple, built-in macOS 13+): adequate for simple node-degree charts but not force-directed graphs.
  - **GraphViz via WebKit**: render Dot/SVG in the existing WebKit pane — zero new dependencies, but limited interactivity.
  - **vis-network / Cytoscape.js via WebKit**: JavaScript graph libraries served by the backend's WebKit pane (already used for `document_view.html`). High interactivity, good performance to ~1000 nodes, well-maintained. Strong candidate for the KG inspector map tab.
  - **RealityKit** (already in scope for Mind Palace, issue #1158): could do 3D node-link diagrams natively, but heavy and Vision Pro-targeted.
  - **Swift Force-directed graph (custom)**: possible via SwiftUI Canvas + spring simulation, but engineering-heavy.
- **Recommendation:** File a `needs-design` issue under KG & Hermeneutics milestone: "KG inspector map tab: evaluate vis-network vs Cytoscape.js vs GraphViz-SVG for the entity graph renderer." The WebKit approach is the lowest-risk path because the WebKit pane infrastructure already exists.

### D2 — Node/graph analysis: PyKEEN + NetworkX already in codebase (underutilized)
- **Finding:** `docs/architecture/api/overview.md` documents `graph_reasoning.py` (NetworkX: centrality, communities, clustering) and `pykeen_inference.py` (link prediction, TransE model training). `docs/architecture/api/KG_ENDPOINTS.md` shows these are wired to `/api/kg/graph/centrality`, `/api/kg/pykeen/train`, `/api/kg/pykeen/predict` — but no SwiftUI surface exposes them.
- **Ideas not yet in issues:**
  - **Community detection display**: show which documents cluster together in the KG (map color to community in the Mind Palace).
  - **Centrality-ranked entity list**: sort the KG entity list by betweenness centrality ("most connected nodes first") — a research-useful default sort order.
  - **Auto-suggest links via PyKEEN predictions**: when a researcher is looking at an entity, show "suggested relations" from link prediction (like "Suggested: Person A → *knows* → Person B, confidence 0.83").
- **Source:** `docs/architecture/api/KG_ENDPOINTS.md` §4 KG analytics, §5 curation loop.
- **Recommendation:** File under KG & Hermeneutics: "KG inspector: surface centrality sort + community color-coding (use existing `/api/kg/graph/centrality` endpoint)."

### D3 — The loupe PDF plan is ready-to-dispatch
- **Finding:** `docs/superpowers/plans/2026-05-25-loupe-pdf-zoom.md` is a complete, checkbox-ready implementation plan (7 tasks, all with exact file paths, code diffs, and commit messages). The image loupe already exists. This plan extends it to PDF.
- **Recommendation:** File the GitHub issue (Section A1), then dispatch a `tier:medium` worker with the plan file path. Estimate: 1 session.

### D4 — Eleventy site is designed but not built
- **Finding:** `docs/superpowers/specs/2026-03-22-build-release-pipeline-design.md` specifies a `fichero/site/` Eleventy static site at `tubb.ca/apps/fichero/`. No such directory exists yet (the Website milestone is open with 0 concrete issues). The spec gives the full file structure (`src/index.md`, `src/faq.md`, `_layouts/base.njk`) and deployment command.
- **Recommendation:** The spec is actionable. File under Website milestone: "Eleventy site scaffold: tubb.ca/apps/fichero/ (hero, download, FAQ, release notes)" and attach the spec as context.

### D5 — ACENET SSH tunnel: upgrade path to Tailscale + mTLS
- **Finding:** `docs/remote-backend-acenet.md` is a solid operational runbook for the current SSH-tunnel approach. It explicitly notes two upgrade paths: Tailscale (for persistent VPN-style access) and mTLS (for multi-user scenarios). Issue #969 tracks the design work.
- **Recommendation:** The runbook is durable KEEP. File under Security milestone (if created) or Infrastructure: "ACENET remote backend: Tailscale integration guide + mTLS design spike."

---

## Summary

| Category | Count |
|---|---|
| New issues to file (Section A) | 7 |
| New milestone proposals (Section B) | 1 (Security) |
| Stale files proposed for deletion (Section C) | 21 files / file groups |
| Notable tools/visualization ideas (Section D) | 5 |

**Top 5 most valuable findings:**

1. **Security milestone gap** (B1): Auth hardening, token management, and remote-access hardening are scattered across Infrastructure + `roadmap` labels with no milestone. The existing issues (#510, #969, #1092) plus the ingest security notes and the ACENET token-copying workaround all point to a coherent "Security" lane that's missing from the milestone roster.

2. **Unified verification gate is untracked** (A2): A fully-designed, approved spec exists (`docs/superpowers/specs/2026-05-20-unified-verification-gate-design.md`) with a ready-to-execute implementation plan, but no GitHub issue was found for it. This is the "one ⌘U covers everything" gate — a high-value Developer Experience deliverable that can be dispatched immediately.

3. **KG visualization framework: no decision made** (D1): The Mind Palace and KG inspector map tab both need a graph renderer, but no doc or issue has committed to one. The WebKit + vis-network/Cytoscape.js path is the lowest-risk given the existing WebKit infrastructure, but the decision is open. Filing a `needs-design` issue now avoids re-litigating it when each milestone reaches that feature.

4. **PDF loupe plan is complete and ready** (D3/A1): `docs/superpowers/plans/2026-05-25-loupe-pdf-zoom.md` is a fully-specced, checkbox-ready implementation plan. No GitHub issue exists for it. One file → one issue → one dispatch.

5. **21 archive/stale files can be deleted** (Section C): The `docs/archive/` tree and `docs/qa/` contain substantial post-0.0.2 detritus that no longer represents current state. Deleting or redirecting these prevents future agents from acting on stale patterns (especially C2 API migration guide, C21 feature-flag design, and C18/C20 QA matrices that reference closed issues).

**Files confirmed as KEEP (durable reference):**
- `docs/CLAUDE.md` — canonical architecture reference
- `docs/agent-workflow/github-conventions.md` — milestone/label/branch conventions
- `docs/agent-workflow/parallel-execution.md` + templates — QA gate workflow
- `docs/architecture/api/overview.md`, `key_files.md`, `development_standards.md`, `KG_ENDPOINTS.md`
- `docs/architecture/swiftui/overview.md`, `key_files.md`, `SWIFTUI_PRINCIPLES.md`, `development_standards.md`, `api_client.md`
- `docs/architecture/overview.md`, `release-process.md`
- `docs/BUNDLING_BACKEND.md`, `docs/SETUP_BUNDLED_BACKEND.md`
- `docs/remote-backend-acenet.md`
- `docs/ingest_overview.md`, `docs/ingest_api.md`, `docs/ingest_best_practices.md`, `docs/supported_file_types.md`
- `docs/superpowers/specs/2026-05-20-unified-verification-gate-design.md`
- `docs/superpowers/specs/2026-03-22-build-release-pipeline-design.md`
- `docs/superpowers/plans/2026-05-25-loupe-pdf-zoom.md` (until dispatched)
- `docs/release-notes-0.0.2.md` (historical record)
- `docs/VALIDATION.md` (needs minor update per A7)
- `docs/archive/swiftui-inspector_redesign.md` (good "why" context, already in archive)
