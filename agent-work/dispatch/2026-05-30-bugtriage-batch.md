# Bugtriage dispatch — 2026-05-30

Your prior session's output (`agent-work/proposals/2026-05-30-issue-triage.md`) is the plan. Execute it + the additions below. No code edits — `gh` CLI + plan documents only. **Worktree:** `~/code/fichero-0.0.2`. **Branch:** `0.0.2`.

## 1. Apply Phase 1 (GH hygiene) from your own plan

From `agent-work/proposals/2026-05-30-issue-triage.md` §7 ("GitHub Projects v2 Reorganization Proposal"):

- Add three custom fields to Project #5 "fichero" (Epic / Status / Priority, single-select, options as listed).
- Close as duplicates with cross-reference comments: **#1327 → #1338**, **#475 → #1334**, **#423 → #375**, **#1303** (env, not code), **#1326 → #1318**.
- Verify+close **#1217** (fix landed in `73856f0d`).
- Bulk-label `roadmap`/`parking-lot` and hide from board: release-gate stubs #488–#515 + #511 #512 #505–#508; future #740, #657, #1092–#1095, #1158–#1161, #374, #375, #378–#380, #461.
- Retire feature-based milestones with 0 closed issues (close with no-further-work note): list in §7 of your plan.
- Keep version milestones: `0.0.2`, `0.0.3 - KG Navigation + Polish`, `0.0.3 - Post-LLM-stack`, `0.0.4 - Local RAG`.
- Bulk-set Epic field per your mapping table.

## 2. Incorporate Daniel's running notes (additions to the plan)

Tag/audit/file as you go:

- **#874** — User-extensible entity types. Daniel says this was `in_progress` in TASKS. Check current state (grep merged PRs, look at TASKS.md task #264, scan `fichero-engine/src/fichero/api/routes/registries.py` + Swift `EntityTypeRegistry`). Either close as done if shipped, or leave open with a short status comment + tag Epic=KG-Single-Path (closest fit) or new Epic=Curation/Settings.
- **#1229** — Reading-surface / toolbar polish. Tag Epic=Onboarding (or new "Inspector-UX"); Priority=P1.
- **#1230** — XCUITest click-through UI test target. Tag Epic=Infrastructure; Priority=P2 (gated by [[feedback_xcuitest_tcc_automation_grant]]).
- **#1231–#1239** — release-data imports. Tag Epic=Importers for #1231 #1232 #1233 #1234 #1235 #1236 #1238; Epic=Importers + sub-tag "xlsx" for #1237; Epic=Infrastructure for #1239 (remote ACENET SSH).
- **#1054** — Search returns every page, needs relevance threshold. Tag Epic=Search-or-new; Priority=P1 (Daniel listed it pending-not-started).
- **#1151** — xfail gated-router tests. Tag Epic=Infrastructure; Priority=P2.

## 3. Release-task housekeeping (Daniel's call: separate repo/issue)

Tasks #157–#165 are notarize/DMG/Sparkle/publish flow. Daniel says these "belong in a separate repo/issue, so can probably be closed or moved." Options:
- **Recommend** option A: open a single tracking issue in `dtubb/fichero-releases` titled "0.0.2 release flow — notarize/DMG/Sparkle/publish" with checklist mirroring tasks #157–#165, link back, then close all 9 tasks in this repo's TASKS.md.
- Document your recommendation in a new section appended to `agent-work/proposals/2026-05-30-issue-triage.md`, but **do not** open/close them yet — wait for Daniel's explicit go.

## 4. Output

Append your work to `agent-work/proposals/2026-05-30-issue-triage.md` under a new `## Execution Log — <timestamp>` section: for each mutation, list `gh` command run + result. Commit + push to `0.0.2`. Comment on each issue you close with the duplicate ref.

**Gate rule:** never `gh issue close` until you've grep-confirmed the merge (`git log origin/main..HEAD | grep "(#N)"`) — see [[feedback_lane_orchestration_lessons]] §4.

When done, write a one-line summary to `agent-work/dispatch/2026-05-30-bugtriage-DONE.md` so the manager can pick it up.
