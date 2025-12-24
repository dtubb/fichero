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