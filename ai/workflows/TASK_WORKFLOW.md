# TASK_WORKFLOW.md

## Task Processing System Overview

Systematic workflow for AI to implement tasks with human oversight, following established checklists and standards.

## Workflow

1. **Select task**
   - Open `ai/TODO.md`
   - If `[>]` exists, that task is in progress, start there
   - Choose highest priority task marked `[ ]` (available)
   - Update task status to `[>]` when starting

2. **Understand task requirements**
   - Read task folder: `ai/tasks/TODO-XXX/`
   - Review `task.md` for step-by-step instructions, if does not exist go to INBOX_WORFKLOW.md and create relevent files. 
      - Ask for human input.
   - Review `human_note.md` for human requirements, if it exists.
   - Review `context.md` for background context, if it does not exist. write it.
   - Ask human if anything is unclear

3. **Create or Copy relevant workflow checklist**
   - Determine task type (API endpoint, feature, bug fix, view, etc.)
   - Copy appropriate checklist from `ai/contexts/[backend|frontend]/workflow_checklist.md`
   - Or update checklist into task folder as `implementation_checklist.md`
   - Customize checklist based on specific task requirements

4. **Follow systematic implementation**
   - Work through checklist phases systematically:
     - Update with [ ], [>], or [x] depending on current step.
     - Planning Phase: Understand requirements and design
     - Implementation Phase: Write code following standards
     - Testing Phase: Verify functionality and edge cases
     - Review Phase: Self-check and prepare for human review
   - Check off items as completed
   - Take notes in `notes.md` for decisions and issues

5. **Apply development standards**
   - Follow best practices from `ai/contexts/[backend|frontend]/development_standards.md`
   - Implement proper error handling
   - Add appropriate logging
   - Follow code style guidelines
   - Write comprehensive tests

6. **Self-review and testing**
   - Verify all checklist items are completed
   - Run relevant tests (unit, integration, UI)
   - Check for errors or issues
   - Verify code follows established patterns
   - Create summary of changes in `summaries/` folder

7. **Human review**
   - Present completed work to human
   - Show files changed and decisions made
   - Show completed checklist with all items checked
   - Request feedback and approval
   - Update based on human input

8. **Finalize and commit**
   - Update task status to `[x]` in TODO.md
   - **Commit changes to Git** with clear commit message following the format in `ai/templates/git_update_template.md`:
    - Run `git add .` to stage all changes
    - Run `git commit -m "<descriptive commit message>"` to commit
    - Run `git push` if ready to push to remote
    - Then STOP.

## Task Structure

```
tasks/TODO-XXX/
├── human_note.md          # Initial human requirements
├── task.md                # Step-by-step instructions with human answers
├── context.md             # Background context (optional)
├── implementation_checklist.md  # Customized workflow checklist
├── notes.md               # AI notes and decisions (optional)
└── summaries/             # Completion reports
```

## Rules

**DO:**
- Follow workflow checklists systematically
- Keep tasks small and focused
- Ask human when unsure about requirements
- Follow established development standards
- Document decisions and changes
- Update checklist as you progress

**DON'T:**
- Skip checklist steps without human approval
- Make changes outside task scope
- Skip human review of completed work
- Create summary files in root directory
- Proceed to next task without explicit confirmation

## Best Practices

- **Systematic approach**: Follow checklists step by step
- **Focused development**: One task at a time
- **Clear documentation**: Update checklist and notes as you work
- **Human oversight**: Review at each major phase
- **Clean structure**: Keep all task-related files in task folder
- **Reference standards**: Use context files for guidance

## Need Help?

- Review appropriate workflow checklist
- Check development standards
- Re-read task requirements
- Ask for clarification on specific steps
- Keep implementation focused and simple