# INBOX_WORKFLOW.md

## Inbox System Overview

Capture new ideas from the inbox and file them as tasks, ensuring organized workflow and proper review.

## Workflow

1. **Check inbox** for new files in `ai/inbox/`:
    - Run `ls ai/inbox/` to list all idea files
2. **Review** the first idea. ignore other ideas.
3. **Determine** logical placement
4. **Ask human** for confirmation
5. **Update TODO.md** with task details
6. **Create** task folder with concise name
7. **Move** inbox file to task folder as `inbox_note.md`
8. **Copy template** `ai/templates/inbox.md` to task folder as `task.md` and update
9. **Request human review** of the completed task setup
10. **Update workflow** based on human feedback and show differences
11. **Confirm changes** with human before finalizing
12. **Commit changes to Git** with clear commit message following the standard format:
    - Run `git add .` to stage all changes
    - Run `git commit -m "<descriptive commit message>"` to commit
    - Run `git push` if ready to push to remote
    - Then STOP.

## Rules

**DO:**
- Update task numbers sequentially
- Give clear, concise names
- Document decisions in chat
- Avoid creating summary documents

**DON'T:**
- Move ideas automatically
- Create tasks without confirmation