# Milestone Audit: Mac App Shell — 2026-05-30

## Summary

| Category | Count |
|---|---|
| Issues audited (open) | 2 |
| Issues audited (closed) | 0 |
| **Keep open as-is** | 0 |
| **Keep open + label fix** | 1 (#520) |
| **Move to different milestone** | 1 (#1341) |
| **Candidates to move IN from other milestones** | 3 (see Section 3) |
| **No-milestone candidates** | 2 (see Section 4) |

Milestone description is accurate and complete. The milestone is severely under-scoped for a Mac shell: only 2 issues tracked, several clear Mac-shell tasks live in other milestones or have no milestone at all.

---

## Section 1 — Issues currently in "Mac App Shell"

### 1A — Label fixes (keep in milestone, update labels)

```bash
# #520: Integrate and test Sparkle auto-update for 0.0.2 release
# Missing: priority label. Sparkle is a ship-gate for 0.0.2 auto-update; P1 is appropriate.
gh issue edit 520 --repo dtubb/fichero --add-label "priority:P1"
# Rationale: type:task + client:swiftui present; priority missing. Every issue should carry type + priority.
```

### 1B — Move to different milestone

```bash
# #1341: Audit + standardize Mac storage paths (Containers / Application Support / Logs)
# Move from "Mac App Shell" → "Infrastructure"
# Rationale: Issue is entirely about backend Python storage-path strings (db.py, models.py,
# storage_snapshots.py, audio_base.py) plus one Swift log path. The work is path-constant
# consolidation and a one-time migration function — classic Infrastructure / backend chore,
# not macOS app chrome. Labels confirm this: backend + type:task + needs-design.
# The Mac App Shell scope (menus, About panel, shortcuts, first-run, window state, Sparkle)
# has no overlap with ~/Library storage-path cleanup.
gh issue edit 1341 --repo dtubb/fichero --milestone "Infrastructure"
```

---

## Section 2 — Closed issues (none)

The milestone has 0 closed issues (confirmed via API). No premature-close recoveries needed.

---

## Section 3 — Candidates to move INTO "Mac App Shell" from other milestones

These issues clearly belong in "Mac App Shell" scope (menus, first-run, window chrome) but are currently assigned elsewhere.

```bash
# #733: First-run wizard: 'Use the cheapest model that works' framing
# Currently: milestone "Search"
# Reason to move: This is a first-run onboarding wizard triggered on first launch when no
# provider is configured — squarely in the Mac App Shell "first-run flow" scope. Its Search
# milestone assignment appears to be an accident of when the issue was created (during a Search
# sprint), not its actual domain. The issue is client:swiftui + type:task.
gh issue edit 733 --repo dtubb/fichero --milestone "Mac App Shell"

# #382: 0.0.1 Regression Gate: imports, window restore, and workflow/transcribe reliability
# Currently: milestone "Infrastructure"
# Note: This is a multi-item regression gate; "window restore" is explicitly listed as a
# child concern (#385). The gate itself may belong in Infrastructure (release process),
# but the window-state restoration child issue (#385) should be in Mac App Shell.
# Recommend: leave #382 in Infrastructure (it's a release gate, not app-chrome work),
# but ensure #385 is correctly tracked.
# ACTION: Check #385 separately (see Section 5).

# #1215: frontend: add reliable toolbar and View menu controls for pane visibility and view modes
# Currently: milestone "Library & Reading Surface"
# Note: The CORE request is a View menu structure + toolbar toggles for pane
# visibility — this is macOS menu chrome. However, the panes being toggled (inspector,
# list, preview, WebKit) are Library & Reading Surface concerns. This is a judgment call:
# the issue is labeled type:bug + priority:P1 + client:swiftui.
# RECOMMENDATION: Leave in "Library & Reading Surface". The menu/toolbar work exists to
# serve the reading surface; it's not standalone app chrome. The milestone description
# includes "View menu" in Mac App Shell, but this issue's primary concern is the surface
# behind the menu, not the menu itself. Flag for manager decision.
# (No command — leave as-is pending manager call.)
```

---

## Section 4 — No-milestone candidates that belong in "Mac App Shell"

```bash
# #296: Later: Sparkle release hosting and auto-update distribution pipeline
# Currently: no milestone, labels: roadmap + type:feature
# Rationale: Sparkle appcast hosting, signing keys, CI step for releases, and update
# channels are the operational completion of Sparkle (#520 above). Natural home is
# "Mac App Shell" (Sparkle is in the milestone description). Could also go in
# "Infrastructure" since it's CI/release ops. Recommend Mac App Shell since it pairs
# directly with #520.
gh issue edit 296 --repo dtubb/fichero --milestone "Mac App Shell"

# #760: Bash-launched Fichero binary doesn't get window/scene activation on macOS 26
# Currently: no milestone, labels: client:swiftui
# Rationale: App launch behavior (window not appearing on direct binary exec) is
# Mac App Shell territory ("app launch" is in the milestone description). The issue
# requests a scripts/launch-release.sh helper + README note. Missing: type label,
# priority label.
gh issue edit 760 --repo dtubb/fichero --milestone "Mac App Shell"
gh issue edit 760 --repo dtubb/fichero --add-label "type:task" --add-label "priority:P3"
# P3 because it's a workaround-documented edge case (Bash exec vs Finder launch),
# not a user-facing bug in normal app operation.
```

---

## Section 5 — Follow-up check recommended

```bash
# #385: New database window restore across relaunch
# (child of #382, referenced in body but not fetched)
# If open and untracked, assign to "Mac App Shell" — window state restoration is
# explicitly in the milestone scope.
gh issue view 385 --repo dtubb/fichero --json number,title,milestone,state
# If open + no milestone or wrong milestone:
# gh issue edit 385 --repo dtubb/fichero --milestone "Mac App Shell"
```

---

## Section 6 — Label-only fixes for issues NOT in this milestone (housekeeping)

These issues are in other milestones but have label gaps relevant to Mac App Shell audit findings:

```bash
# #733 (if moved to Mac App Shell per Section 3): missing priority label
gh issue edit 733 --repo dtubb/fichero --add-label "priority:P2"
# Rationale: First-run wizard is important UX but not a ship-blocker. P2 is appropriate.

# #296 (if moved to Mac App Shell per Section 4): labels are roadmap + type:feature, no priority
gh issue edit 296 --repo dtubb/fichero --add-label "priority:P3"
# Rationale: Sparkle hosting pipeline is future operational work, not current sprint.
```

---

## Tricky Cases for Manager

1. **#1341 milestone placement**: The issue has `backend` label and touches only Python files + one Swift log path. It's in "Mac App Shell" because storage paths include the macOS Containers path, but the actual fix is backend-side. Infrastructure is the better fit. High confidence move.

2. **#1215 View menu / toolbar** (Library & Reading Surface): The View menu is called out in the Mac App Shell milestone description, but this issue's primary deliverable is the reading-surface pane layout, not standalone app chrome. Could legitimately live in either milestone. Left in Library & Reading Surface pending manager decision.

3. **#733 First-run wizard** (Search milestone): Strongly belongs in Mac App Shell by content (first-run flow). Appears to have been filed during a Search sprint and milestone-assigned by context rather than domain.

4. **#296 Sparkle hosting** (no milestone): This is release-operations work (CI, appcast, signing keys) that could reasonably go in Infrastructure or Mac App Shell. Recommended Mac App Shell because it's the companion to #520 and both are about Sparkle.

5. **Milestone sparseness**: After moves, "Mac App Shell" would have ~4-5 active issues for an entire app-chrome milestone. Consider whether more Mac App Shell work exists as untracked implicit work (keyboard shortcut cheat sheet, About panel content, Help menu wiring, toast/notification system, progress indicators) that needs issues created.
