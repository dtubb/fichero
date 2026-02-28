# Fichero Agent Plan

## Overview
This plan governs the autonomous and semi-autonomous management of the Fichero project folder.

## Objectives
1. Maintain code quality and architectural integrity.
2. Progress through the `TODO.md` backlog efficiently.
3. Ensure synchronization between SwiftUI frontend and Python backend.
4. Provide regular status updates to Daniel.

## Recurring Tasks (Cron)
- **Every 30 Minutes:**
    - Scan `TODO.md` for high-priority (P0/P1) tasks.
    - Check `docs/agent-workflow/inbox/` for new human requests.
    - **Self-Correction**: If the inbox has items, pause all active coding and process the inbox into `TODO.md` immediately.
    - Verify backend/frontend sync (OpenAPI schema).
    - Run SwiftLint and Python tests if changes were made.
    - Update `memory/` log with a status summary.


## Release Milestones (v1.0)

### Milestone 0: Core Foundation (v0.0.1)
- **Goal**: Perfect the document management and ingestion foundation. Disable advanced/incomplete features to ensure a stable core.
- [ ] **Feature Flagging**: Implement a `FeatureManager` system to toggle major modules (Workflows, Agents, Automation, MCP).
    - **Mechanism**: Use a central `@Published` manager that can be toggled by the GUI.
    - **GUI Enforcement**: Use the manager to prune the Sidebar, Menu Bar, and Toolbars.
- [ ] **v0.0.1 Scope**:
    - [x] Document Library (Icons, List, Table views).
    - [x] Metadata & Text Extraction.
    - [x] Basic Search.
    - [ ] Stabilize Document Move/Rename.
    - [ ] Solidify @SceneStorage persistence for v0.0.1 features.
- [ ] **Disabled by Default**: Hide Workflows, Automation, Activity, and MCP from Sidebar and Menus for 0.0.1 release.

## Milestone 1: Stability & Data Integrity (v0.1.0)

### Milestone 2: Feature Completeness
- [ ] Finish Sidebar UX improvements (Folder support for workflows, flat automation list).
- [ ] Enable Universal Creation (Create commands work from any mode).
- [ ] Implement Contextual Batch Triggering for all file types.
- [ ] Refactor DocumentInspector and NodePopover for production-grade reliability.

### Milestone 3: Distribution & QA
- [ ] Finalize Backend Bundling strategy for macOS distribution.
- [ ] Conduct comprehensive E2E workflow testing (Infrastructure Phase 10D).
- [ ] Complete AppleScript support for automation enthusiasts.
- [ ] zero SwiftLint warnings across the entire codebase.

## Task Management Strategy

- **Inbox Processing**: Every 30 minutes, I check `docs/agent-workflow/inbox/`. If new ideas exist, I convert them into structured tasks in `TODO.md` following the `INBOX_WORKFLOW.md`.
- **Master Task List**: `TODO.md` is the source of truth. I never deviate from it without updating it first.
- **Task Folders**: For complex tasks, I create a dedicated folder in `docs/agent-workflow/tasks/TODO-XXX/`.
    - **`task.md`**: Each folder contains a `task.md` following the `TASK_SPECIFICATION.md` template. This serves as the local plan for that specific task.
    - **Execution**: I check the `task.md` at the start of every session to resume exactly where I left off.

- **Reporting**: I report progress via Slack at the completion of each P0/P1 task or when the inbox is cleared.


## Success Metrics
- 0 SwiftLint warnings.
- 100% passing rate for Python and Swift tests.
- Timely completion of `TODO.md` milestones.
