# Simple Development Workflow

## Quick Start

4. **Find a task** - Choose the one the Human requested. Or Pick In Progress task `[>]` or first `[ ]` (available) tasks in TODO.md
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