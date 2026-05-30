# Milestone Audit — Developer Experience
**Date:** 2026-05-30  
**Auditor:** claude-sonnet-4-6  
**Milestone:** Developer Experience (milestone #64)  
**Scope:** contributor/agent docs + tooling (build scripts, CI, OpenAPI round-trip, jcodemunch config, test gates)

---

## Summary

| Category | Count |
|---|---|
| Total issues in milestone | 1 |
| Keep open as-is | 0 |
| Keep open + label-fix | 1 |
| Re-milestone INTO Developer Experience (from other milestone/none) | 3 (proposed) |
| Close | 0 |
| Reopen closed | 0 |
| Label-only fixes | 1 |

**Tricky case for manager decision:** Three issues currently in Infrastructure or no-milestone are strong DX candidates (XCUITest tooling, /bug skill). Whether to re-milestone them is a judgment call — they involve test infrastructure and contributor tooling, which is DX's stated scope, but they may be intentionally in Infrastructure. See "Manager Decisions" at the end.

---

## Issues Audited (currently in Developer Experience)

### #1299 — Visual verification: #Preview snapshots via Xcode MCP RenderPreview + XCUITest target (pending TCC grant)
- **State:** OPEN
- **Labels:** _(none)_
- **Milestone:** Developer Experience ✓ (correct — agent/contributor visual verification tooling)
- **Body summary:** Two-path plan: Path A (RenderPreview, works now), Path B (XCUITest headless, blocked on one-time macOS TCC grant for Accessibility + Automation). References #1230/#1242 as XCUITest sub-issues.

**Recommendation: keep open; fix labels**

---

## Action Checklist

### LABEL FIXES (open issues, no milestone change)

```sh
# #1299: Add type:task (it's a tooling/testing setup task), priority:P2, and needs:human
# (Path B is blocked on a human TCC grant — Daniel must go to System Settings → Privacy;
# Path A is already agent-executable but the umbrella issue tracks both paths)
gh issue edit 1299 --repo dtubb/fichero \
  --add-label "type:task" \
  --add-label "priority:P2" \
  --add-label "needs:human"
```

---

## MANAGER DECISIONS — Proposed Re-Milestoning (requires your call)

These issues are NOT in Developer Experience today but belong there per the milestone description ("everything for the people BUILDING Fichero — docs and tooling combined ... Tooling: build scripts, test gates, CI hooks").

### Candidate A: #1230 — Add XCUITest click-through UI test target (launch + reading-surface smoke tests)
- **Current milestone:** Infrastructure
- **Current labels:** _(none)_
- **Why DX:** This is test infrastructure for contributors/agents — adds the XCUITest target (a build/test gate), not a user-facing feature. It is explicitly referenced as a sub-issue of #1299 which is already in Developer Experience.
- **Counterargument:** It directly tests user-facing reading-surface flows; Infrastructure is plausible.

```sh
# If you agree it's DX:
gh issue edit 1230 --repo dtubb/fichero \
  --milestone "Developer Experience" \
  --add-label "type:task" \
  --add-label "priority:P2" \
  --add-label "client:swiftui"
```

### Candidate B: #1242 — #1230 follow-up: XCUITest flows 2-4 (seeded-backend reading-surface click-through)
- **Current milestone:** none
- **Current labels:** _(none)_
- **Why DX:** Follow-on work to #1230; same reasoning. Also needs a seeded test library infra piece (library-override launch argument) that is pure contributor tooling.

```sh
# If you agree it's DX:
gh issue edit 1242 --repo dtubb/fichero \
  --milestone "Developer Experience" \
  --add-label "type:task" \
  --add-label "priority:P2" \
  --add-label "client:swiftui"
```

### Candidate C: #478 — Bug reporting system: /bug skill + structured GitHub issue template
- **Current milestone:** Infrastructure
- **Current labels:** `type:task`, `backend`
- **Why DX:** The /bug skill is a Claude Code skill (contributor/agent tooling), and the GitHub issue template is contributor workflow infrastructure — both are exactly what Developer Experience describes.
- **Counterargument:** Has `backend` label suggesting some server component; Infrastructure is defensible.

```sh
# If you agree it's DX:
gh issue edit 478 --repo dtubb/fichero \
  --milestone "Developer Experience"
# (keep existing labels; consider removing 'backend' if the in-app button component is scoped out)
```

---

## Issues NOT Recommended for Re-Milestoning (reviewed and left alone)

| Issue | Title | Milestone | Why NOT moved to DX |
|---|---|---|---|
| #1317 | E2E test: full book tubb2020shift.pdf catalogue + KG end-to-end | none | Integration/regression test against a specific corpus — closer to Workflows or KG & Hermeneutics; not contributor tooling |
| #1324 | Testing: surface dev tier so all features are visible during 0.0.2 testing | none | Short-lived 0.0.2 testing toggle; not a durable DX tool |
| #479 | Frontend wiring architecture: feature gates, testing system, and release pipeline | none | Broader architecture than DX; release pipeline → Infrastructure is correct |
| #1133 | AppleScript bridge: programmatic UI control for autonomous dev/test loop | Infrastructure | Autonomous dev tooling but primarily SwiftUI/app feature, not contributor docs or build infra |

---

## Observation: Thin Milestone

The Developer Experience milestone was created recently (2026-05-30) as part of the GH conventions overhaul. With only 1 issue it reflects the milestone being newly scoped rather than a backlog gap. The convention work itself (docs in `docs/agent-workflow/`, `docs/architecture/`) was done as commits without tracking issues. No action required, but the manager may want to file a small batch of "write/update X doc" issues to populate it.
