# Fichero Development Tasks (Implementation Order)

## Legend
- `[ ]` = Available (ready for implementation)
- `[>]` = In Progress (currently being worked on)
- `[x]` = Completed (done)

## How to Use
1. **Check Current Tasks**: Look for `[>]` (in progress) first
2. **Pick Next Task**: If no `[>]`, pick first `[ ]` from top
3. **Mark In Progress**: Update `[ ]` to `[>]` when starting
4. **Navigate to Task**: `cd ai/tasks/[feature]/TODO-XXX/`
5. **Read Files**: `task.md`, `context.md`, `workflow.md`
6. **Implement**: Follow workflow instructions
   - Take notes in `notes.md` (create if needed)
   - Break down steps in `task.md` checklist
   - Update files as you progress
7. **Complete**: Update `[>]` to `[x]` and move to completed

## 1. Backend API (Foundation - Must be done first)
- [ ] TODO-004: Complete File Import Endpoint
- [ ] TODO-005: Complete Document Move Endpoint

## 2. Frontend Features (Built on backend)
- [ ] TODO-001: Complete Inline Rename Functionality
- [ ] TODO-002: Complete New Folder Creation
- [ ] TODO-003: Enhance Drag and Drop Visual Feedback
- [x] TODO-008: Add keyboard shortcuts for CRUD operations
- [x] TODO-009: Create inline rename and new folder dialogs
- [ ] TODO-010: Add Batch Operations
- [ ] TODO-011: Enhance Search Functionality

## 3. AI & Workflow (Depends on backend + frontend)
- [ ] TODO-006: Implement AI-Powered Document Analysis
- [ ] TODO-007: Complete Workflow Engine

## 4. Infrastructure (Can be done in parallel)
- [ ] TODO-012: Improve Error Handling
- [ ] TODO-013: Add Comprehensive Logging
- [x] TODO-014: Fix compilation errors and warnings
- [x] TODO-015: Update development process documentation

## 5. Foundational (Already completed)
- [x] TODO-000: Implement comprehensive drag and drop functionality