# INBOX_WORKFLOW.md

## Inbox System Overview

Capture new ideas from the inbox and file them as tasks, ensuring organized workflow and proper review.

## Workflow

1. **Check inbox** for new files in `ai/inbox/`:
    - Run `ls ai/inbox/` to list all idea files
2. **Review** the first idea. ignore other ideas.
3. **Determine** logical placement
4. **Do not Ask human** for confirmation. Make best guess.
5. **Update TODO.md** with task details
6. **Create** task folder with concise name
7. **Move** inbox file to task folder as `human_note.md`
8. **Add** copy of `ai/templates/todo/task.md` as `task.md` to task folder. Review `ai/contexts` as needed to update tasks.md note.
9. **Add** copy of `ai/templates/context.md` as `context.md`to task folder. Review `ai/contexts` and tasks.md as needed to update context.md note.
9. **Do not request human review of `tasks.md`** and `context.md`. Make best guess and proceed.
11. **Commit changes to GitHub** with clear commit message following the format in `ai/templates//git_update_template.md`:
12. **Don't forget to commit to GitHub.**
12. **Do not Request human review of task files**.
13. **UNDER NO CIRCUMSTANCES PROCEED TO IMPLEMENT TASK, UNLESS REQUESTED. ONCE POSTED TO GIT GO BACK TO AI_README.md to continue.**
14. **STOP WHEN TASK IS DONE**


## Rules

**DO:**
- Update task numbers sequentially
- Give clear, concise names
- Document decisions in chat
- Avoid creating summary documents

**DON'T:**
- Move ideas automatically
- Create tasks without confirmation