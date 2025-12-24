# Complete Development Workflow

## Overview

This document describes the systematic development process for the Fichero project.

## Task Status

- `[ ]` = Available (ready for implementation)
- `[>]` = In Progress (currently being worked on)
- `[x]` = Completed (done - keep in place for reference)

## Workflow Steps

### 1. Task Selection

**Priority Order:**
1. Check for any `[>]` (in-progress) tasks first
2. If none, pick first `[ ]` (available) task from TODO.md
3. Follow implementation order (backend → frontend → AI → infrastructure)

**How to Pick:**
- Read `TODO.md` for available tasks
- Tasks organized by feature categories
- Pick task that matches your capabilities

### 2. Task Preparation

**Navigate to Task:**
```bash
cd ai/tasks/TODO-XXX/
```

**Verify Task Files:**
- `task.md` - Task definition and checklist
- `context.md` - Task-specific context
- `workflow.md` - Implementation workflow
- If any file missing: STOP and request human creation

**Read Files Carefully:**
- Understand requirements in `task.md`
- Review technical context in `context.md`
- Follow steps in `workflow.md`

### 3. Implementation

**Implementation Steps:**
1. Review existing codebase
2. Implement according to specifications
3. Add proper error handling
4. Write unit and integration tests
5. Update documentation

**Best Practices:**
- Follow project conventions
- Use specified context files
- Follow workflow template
- Take notes in `notes.md`

### 4. Testing

**Testing Requirements:**
- Run all specified tests
- Test edge cases
- Verify error handling
- Check performance

**Quality Checklist:**
- [ ] All tests pass
- [ ] No warnings/errors
- [ ] Code review approved
- [ ] Documentation complete

### 5. Completion

**Final Steps:**
1. Self-review code
2. Run linters
3. Request human review
4. Address feedback
5. Update TODO.md status
6. Keep task in place (no need to move)

## Task Management

### Creating New Tasks

**Using Scripts:**
```bash
python scripts/generate_task.py TODO-XXX "Task Name" "Description"
```

**Manual Creation:**
```bash
mkdir tasks/TODO-XXX
cp templates/* tasks/TODO-XXX/
# Edit files with specifics
# Add to TODO.md
```

### Task File Structure

```
tasks/TODO-XXX/
├── task.md          # Task definition with checklist
├── context.md       # Task-specific context
├── workflow.md      # Implementation workflow
├── notes.md         # (Optional) Implementation notes
└── resources/       # (Optional) Task resources
```

## Critical Rules

1. **Never** work on undefined tasks
2. **Always** check TODO.md first
3. **Follow** the specified workflow
4. **Request** human review before committing
5. **Update** all status indicators

## Example Workflow

```
1. Read WORKFLOW.md
2. Check TODO.md for [>] or [ ] tasks
3. Open tasks/TODO-001/
4. Follow task instructions
5. Test and review
6. Update status to [x]
```

## Getting Help

- Re-read this workflow
- Check task files
- Request human assistance
- Never proceed without understanding