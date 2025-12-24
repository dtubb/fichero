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
7. **Move** inbox file to task folder as `human_note.md`
8. **Add** copy of `ai/templates/inbox_note.md` as `inbox_note.md` to task folder. Review `ai/contexts` to write note.
9. **Request human review of `inbox_note.md`**
10. **Copy contents** of `ai/templates/task` to task folder, and update each file based on `inbox_task.md` and `human_note.md`
11. **Commit changes to Git** with clear commit message following the standard format:
    - Run `git add .` to stage all changes
    - Run `git commit -m "<descriptive commit message>"` to commit
    - Run `git push` if ready to push to remote
    - Then STOP.
12. **Request human review of task files**.
13. **UNDER NO CIRCUMSTANCES PROCEED TO IMPLEMENT TASK, UNLESS REQUESTED. STOP ONCE POSTED TO GIT.**

## Rules

**DO:**
- Update task numbers sequentially
- Give clear, concise names
- Document decisions in chat
- Avoid creating summary documents

**DON'T:**
- Move ideas automatically
- Create tasks without confirmation