# Agent Workflow Guide

**Fichero**: Document management and AI processing for macOS. Organize, search, chat, and run AI workflows on documents.

This folder documents the lightweight agent workflow used in this repo. For project context, see `README.md`.

## Quick Start

### Smart Mode Selection:

**Step 1: Check for inbox items**
```bash
ls docs/agent-workflow/inbox/
```
- **If files exist** -> Enter Inbox Mode (Option 1)
- **If empty** -> Enter Task Mode (Option 2)

**Option 1: Inbox Mode**
1. Follow `docs/agent-workflow/workflows/INBOX_WORKFLOW.md` completely. Process only one inbox idea at a time.
2. Stop when inbox processing is done. 
3. Commit to GitHub, if not already committed. Use `docs/agent-workflow/templates/git_update_template.md`.

**Option 2: Task Mode**
1. Follow `docs/agent-workflow/workflows/TASK_WORKFLOW.md` completely. Complete only one task.
2. Stop when task is done.
3. Commit to GitHub, if not already committed. Use `docs/agent-workflow/templates/git_update_template.md`.

### Key Principles
- **Save context** - Only enter Inbox Mode if items exist
- **One mode at a time** - Complete chosen mode fully
- **Don't switch modes** - Either Inbox Mode OR Task Mode
- **Ask human when blocked** - Make a best guess when safe, or add an inbox note for follow-up.

## Rules

- **No emoji** - Use clear text only
- **Small tasks** - Break complex work into simple, focused tasks
- **Clear instructions** - Make task files easy to understand and concise
- **One mode at a time** - Complete Inbox Mode OR Task Mode fully then stop
- **Ask human** - Request input when unsure about critical decisions
- **Clean structure** - Keep root directory clean, put summaries and documentation in task folders
- **Follow workflows** - Use the provided workflow documents as guides
- **Save context** - Only process inbox if items actually exist

## Folder Structure

```
docs/agent-workflow/
├── README.md                  # This file
├── TODO.md                    # Master task list
├── inbox/                     # New planning notes
├── templates/                 # Reusable task templates
└── workflows/                 # Process playbooks
```

Architecture and implementation docs live in `docs/architecture/`.
Historical task artifacts were moved out of the repo to delete staging.
