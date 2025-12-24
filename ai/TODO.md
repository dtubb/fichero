# Todo List to Manage AI Tasks

## IMPORTANT RULES - READ FIRST!

### DON'T REWRITE THIS FILE
- **Never** overwrite or recreate TODO.md from scratch
- **Always** use search/replace or careful editing. Do not re-order.
- **Ask human** if you're unsure about changes

### HOW TO UPDATE PROPERLY
1. **Check inbox first** - See `ai/inbox/INBOX_WORKFLOW.md` for complete instructions
2. **File ideas logically** - Put them where they belong (ask human for confirmation)
3. **Edit carefully** - Use search/replace, test changes
4. **Preserve structure** - Keep existing formatting and sections

## Legend
- `[ ]` = Available (ready for implementation)
- `[>]` = In Progress (currently being worked on)
- `[x]` = Completed (done - keep for reference)
- `[!]` = Blocked (dependent on other tasks)

## Priority Levels
- `P0` = Critical path, must be done immediately
- `P1` = High priority, should be done soon
- `P2` = Medium priority, can wait
- `P3` = Low priority, nice to have

## Task Categories
- `Backend`: Backend API and services
- `Frontend`: UI and user interaction
- `AI`: Machine learning and workflows
- `Infrastructure`: Cross-cutting concerns
- `Documentation`: Documentation improvements

## Rules for Task List
- Update in place.
- Don't reorder.

## AI Task Management [P0]

- [x] TODO-016: Implement ai folder with TODO.md, README.md, and WORKFLOW.md
- [x] TODO-020: Review and improve AI context documents organization (P2, Medium)
  - Depends on: None

## Backend API (Foundation) [P0]

### File Management
- [ ] TODO-004: Complete File Import Endpoint (P1, Medium)
  - Depends on: None
- [ ] TODO-005: Complete Document Move Endpoint (P1, Medium)
  - Depends on: TODO-004

## Frontend Features (Built on backend) [P1]

## Foundational [P3]

### Sidebar Functionality
- [ ] TODO-001: Review status of sidebar in Frontend
- [ ] TODO-002: Complete In Line Rename (P1, Medium)
- [ ] TODO-003: Complete New Folder Creation (P1, Medium)
- [ ] TODO-004: Enhance Drag and Drop Visual Feedback (P2, Medium)
- [ ] TODO-005: Confirm keyboard shortcuts for CRUD operations (P2, Low)

### Enhanced Features
- [ ] TODO-007: Enhance Search Functionality (P2, High)

## AI & Workflow (Depends on backend + frontend) [P2]
- [ ] TODO-007: Plan Workflow Engine (P1, High)

## Infrastructure (Can be done in parallel) [P2]
- [ ] TODO-012: Improve Error Handling (P1, Medium)
- [ ] TODO-013: Add Comprehensive Logging (P1, Medium)
- [x] TODO-014: Fix compilation errors and warnings (P0, Low)
- [x] TODO-015: Update development process documentation (P0, Medium)
- [x] TODO-017: Write concise 100-character summaries for README files (P2, Low)
- [X] TODO-018: Update TASK_WORKFLOW.md to be more concise with human review and Git steps (P1, Medium)
- [x] TODO-019: Update context documents to reflect current application state (P1, Medium)