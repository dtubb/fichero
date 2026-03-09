# STATE.md — Fichero

Last updated: 2026-03-09

## Current Branch

`codex/workflow-ui-sparkle-title` (in progress; PR-first workflow)

## Source of Truth

- Scope/status/priorities are on GitHub only:
  - Milestones: https://github.com/dtubb/fichero/milestones
  - Issues: https://github.com/dtubb/fichero/issues
  - Project: https://github.com/users/dtubb/projects/5
- Local `PLAN.md`/`TASKS.md` are pointer files only.
- Delivery process (Daniel request): ship incremental changes via GitHub PRs continuously; avoid long-lived unpushed local-only change sets.

## 0.0.1 Sprint Focus

Use issue `#279` as the release gate checklist:
- https://github.com/dtubb/fichero/issues/279

Required 0.0.1 product surface:
- ON: Library core, Search core, Workflows, Workflow Execution, Activity, required Settings/Providers path
- OFF (later): Conversations/Chat, MCP menu/surfaces, Integrations menu/surfaces, Library advanced views, icon-view zoom toolbar controls

## Completed This Session

- 2026-03-08 hourly automation run: startup checks completed, no issue execution due to dirty-source-files-on-main hard gate.
- Governance consistency check completed: `AGENTS.md` still states "Phase 0 planning/no coding" while `MEMORY.md` + current issue flow indicate active M0 execution; requires Daniel-level clarification before autonomous implementation resumes.
- Sparkle updater integrated (menu + package wiring) and follow-up release config issue created: `#278`
- Governance updated: GitHub is authoritative; local planning files deprecated
- Milestone alignment updated:
  - Workflows moved into `0.0.1`
  - Chat/conversation items moved out of `0.0.1`
- Feature-gating updates for 0.0.1:
  - Workflows ON by default
  - Activity ON by default
  - Chat OFF by default
  - MCP OFF by default
  - Integrations OFF by default
  - Library icon zoom toolbar controls OFF by default
- Later-milestone follow-up issues created:
  - `#280` (Integrations menu re-enable)
  - `#281` (Icon zoom toolbar re-enable)

## Active Risks / Blockers

- `/session-start-auto` gate is blocked: `main` has dirty source files (`.swift`, `.py`, `.sh`, generated/schema files). Autonomous issue execution cannot continue until these changes are either committed by a human-owned workflow or moved off `main`.
- Governance conflict: phase policy docs disagree (`AGENTS.md` says remain in Phase 0 planning; `MEMORY.md` + `#279` workflow imply Phase 1/M0 execution is active). Treat as blocked for autonomous coding until Daniel confirms canonical policy.
- Xcode package artifact instability around Sparkle XCFramework in DerivedData (intermittent missing artifact)
- Swift package plugin validation drift when package versions move unexpectedly
- Build DB lock errors when concurrent Xcode builds run

## Next Session — Start Here

1. Read `memory/handoff-2026-03-09.md` and clear the dirty-source-files-on-main gate first.
2. Resolve phase-policy conflict (`AGENTS.md` vs. current M0 execution docs) with Daniel before autonomous coding.
3. After both gates are cleared, continue executing `#279` checklist top-down; keep project statuses in sync.
4. Stabilize build reproducibility:
   - resolve Sparkle artifact/cache behavior
   - resolve/lock package plugin validation path
5. Close remaining 0.0.1 gating issues (`#232`, `#233`, `#235`, `#263`, `#278`).
6. Drive QA gate issues to sign-off (`#114`, `#115`, `#116`, `#117`, `#238`, `#250`).
