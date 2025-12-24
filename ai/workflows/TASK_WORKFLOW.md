# TASK_WORKFLOW.md

## Task Processing Workflow

This workflow provides clear instructions for AI to implement tasks with human oversight.

## Workflow Steps

2. **Select task**
   - Open `ai/TODO.md`
   - If `[>]` exists, that task is in progress, start there.
   - Choose highest priority task marked `[ ]` (available)
   - Update task status to `[>]` when starting

3. **Understand task**
   - Read task folder: `ai/tasks/TODO-XXX/`
   - Review files for step-by-step instructions.
   - REview context if requried.
   - Ask human if anything is unclear

4. **Implement solution**
   - Follow steps in `task.md`
   - Keep changes focused and simple
   - Test as you implement
   - Take notes in `notes.md` if helpful

5. **Self-review**
   - Verify all steps are completed
   - Check for errors or issues
   - Run relevant tests
   - Create summary of changes

6. **Human review**
   - Present completed work to human
   - Show files changed and decisions made
   - Request feedback and approval
   - Update based on human input

7. **Finalize and commit**
   - Update task status to `[x]` in TODO.md
   - Commit changes with clear message:
     - Run `git add .` to stage changes
     - Run `git commit -m "<descriptive message>"`
     - Run `git push` if ready
   - Then STOP and wait for next task

## Task Structure

```
tasks/TODO-XXX/
├── task.md          # Step-by-step instructions
├── context.md       # Background (optional)
├── workflow.md      # Implementation details (optional)
├── notes.md         # AI notes (optional)
└── summaries/       # Completion reports
```

## Rules

**DO:**
- Keep tasks small and focused
- Ask human when unsure
- Follow existing patterns
- Document decisions

**DON'T:**
- Create tasks without confirmation
- Make large, complex changes
- Skip human review
- Create summary files in root directory

## Best Practices

- **Consistent structure**: Follow standardized formats
- **Focused development**: One task at a time
- **Clear documentation**: Update as you work
- **Human oversight**: Review at key points
- **Clean structure**: Put summaries in task folders

## Need Help?

- Re-read this workflow
- Check task files
- Ask for clarification
- Keep it simple and focused