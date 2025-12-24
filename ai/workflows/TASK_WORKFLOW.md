# Simple Development Workflow

## Quick Start

4. **Find a task** - Choose the one the Human requested, or choose In Progress task `[>]` or pick first `[ ]` (available) tasks in TODO.md
5. **Follow the steps below** to preapre each task. Make sure it has clear instructions.
6. **Ask questions** - Request human input when needed. Ask them to update specific files, or update files youurself.
7. **Complete and update** - Mark task as `[x]` when done

## Task Status

- `[ ]` = Available (ready to work on)
- `[>]` = In Progress (currently being worked on)
- `[x]` = Completed (done)

## Simple Workflow

### 1. Check the Inbox First
- **See complete instructions**: `ai/inbox/INBOX_WORKFLOW.md`
- Look in `ai/inbox/ideas/` for new feature ideas
- **If you find ideas**: File them in the right place
- Put ideas where they logically belong (TODO.md, planned, etc.)
- **Double check with human** if unsure about placement

### 2. Find a Task to Work On
- Open `ai/TODO.md`
- Look for tasks marked `[ ]` (available)
- If you see `[>]`, that task is already in progress

### 3. Understand the Task
- Each task has a folder: `ai/tasks/TODO-XXX/`
- Read `task.md` - Simple list of what to do
- Read `context.md` - Background information (if needed)
- **Ask if unclear** - Request human input

### 3. Do the Work
- Follow the steps in `task.md`
- Keep it simple - one small thing at a time
- Take notes if helpful
- Test as you go

### 4. Finish Up
- Self-check your work
- Create completion summary in task folder
- Update `TODO.md` - Change `[ ]` to `[x]`
- Move to next task

## Task Structure

```
tasks/TODO-XXX/
├── task.md          # Simple step-by-step list
├── context.md       # Background (optional)
├── workflow.md      # Implementation steps (optional)
├── notes.md         # Your notes (optional)
└── summaries/       # AI summaries and completion reports
```

**AI Summaries:**
- **Keep root directory clean** - No summary files in `ai/` root
- **Put all AI documentation in task folders** - Use `tasks/TODO-XXX/summaries/`
- **Number summaries sequentially** - Use format: `01_DESCRIPTION.md`, `02_DESCRIPTION.md`
- Use clear descriptive names like `01_AI_FOLDER_SIMPLIFICATION_SUMMARY.md`
- Include what was done, files changed, verification, and decisions made
- Helps track progress, provides documentation, and maintains clean structure

**Keep Structure Clean:**
- ❌ Don't create summary files in `ai/` root directory
- ✅ Do put all AI-generated documentation in task summaries folders
- ✅ One task folder = one logical unit with all related documentation

## Rules

1. **Start simple** - Pick small tasks first
2. **Ask questions** - When in doubt, request human input
3. **Keep it focused** - One task at a time
4. **Update status** - Mark tasks as completed

## Need Help?

- Re-read this workflow
- Check the task files
- Ask for clarification
- Keep tasks small and simple

# Development Workflow Guide

## Overview

This guide describes the systematic development process used in the Fichero project, combining AI assistance with human oversight for consistent, high-quality development.

## Development Cycle

```
Select TODO → Load Context → Plan Implementation → Implement Solution → 
Run Tests → Human Review → Lint & Format → Human Approval → Commit Changes → 
Update Task Status → Next Task
```

## Phase Details

### 1. Task Selection
- Review TODO.md for highest priority task (ordered by priority)
- Read detailed task file in `ai/todos/TODO-XXX.md`
- Check dependencies are completed
- Update task status to "in-progress"

### 2. Context Loading
- Load appropriate context file from `ai/contexts/`
- Review task-specific patterns and best practices
- Examine existing codebase structure

### 3. Implementation Planning
- Create detailed implementation plan
- Identify files to be modified
- Define API endpoints (backend) or views (frontend)
- Plan testing strategy

### 4. Solution Implementation
- Follow patterns from context files
- Implement backend API endpoints (if needed)
- Implement frontend views and services (if needed)
- Add proper error handling and logging
- Write comprehensive tests

### 5. Testing
- Run unit tests for business logic
- Run integration tests for API endpoints/UI flows
- Test error conditions and edge cases
- Verify performance characteristics

### 6. Human Review
- Code quality and structure review
- Error handling completeness check
- Test coverage adequacy verification
- Documentation completeness review
- Performance considerations evaluation

### 7. Linting and Formatting
- Run Python linters (black, isort, flake8)
- Run Swift linters (SwiftLint)
- Fix formatting issues
- Verify code style compliance

### 8. Human Approval
- Final code review
- Approval for commit
- Rejection sends back to implementation phase

### 9. Commit Changes
- Create feature branch with standardized naming
- Commit with standardized message format
- Push to remote repository
- Create pull request if needed

### 10. Task Completion
- Update task status to "completed" in `ai/todos/TODO-XXX.md`
- Add completion date
- Clean up temporary files
- Move to next highest priority task

## Task Organization

Each TODO item has its own file in `ai/todos/`:

```markdown
# TODO-[ID]: [Feature Name]

## Status
- Status: pending | in-progress | completed | blocked
- Priority: high | medium | low
- Feature Area: backend | frontend | ai | ui | workflow | search | chat | infrastructure

## Details
- Dependencies: [list of TODO IDs]
- Related Files: [list of files to be modified]
- Checklist:
  - [ ] Implementation step 1
  - [ ] Implementation step 2
  - [ ] Testing step 1
  - [ ] Testing step 2
  - [ ] Documentation update
```

## Best Practices

### Consistent Structure
- Follow standardized TODO format
- Use consistent naming conventions
- Maintain uniform code style

### Focused Development
- Use task-specific context files
- Follow phase-based workflow
- Implement systematic quality checks

### Comprehensive Testing
- Write tests for all functionality
- Test error conditions and edge cases
- Verify performance characteristics

### Clear Documentation
- Update documentation with each feature
- Add docstrings to public functions
- Document API changes and breaking changes

### Human Oversight
- Review at critical checkpoints
- Provide approval for commits
- Maintain quality standards