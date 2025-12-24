# AI_README.md

**Fichero**: Document management and AI processing for macOS.

You are an AI to help with building Fichero. If you need more context, see README.md.

## Quick Start

### Smart Mode Selection:

**Step 1: Check for inbox items**
```bash
ls ai/inbox/ideas/
```
- **If files exist** → Enter Inbox Mode (Option 1)
- **If empty** → Enter Task Mode (Option 2)

**Option 1: Inbox Mode**
1. Follow `ai/inbox/INBOX_WORKFLOW.md` completely
2. Stop when inbox processing is done

**Option 2: Task Mode**
1. Follow `ai/WORKFLOW.md` completely
2. Stop when task is done

### Key Principles
- **Save context** - Only enter Inbox Mode if items exist
- **One mode at a time** - Complete chosen mode fully
- **Don't switch modes** - Either Inbox Mode OR Task Mode
- **Ask human** - When unsure about anything

## Rules

- **No emoji** - Use clear text only
- **Small tasks** - Break complex work into simple, focused tasks
- **Clear instructions** - Make task files easy to understand and concise
- **One mode at a time** - Complete Inbox Mode OR Task Mode fully before switching
- **Ask human** - Request input when unsure about anything
- **Clean structure** - Keep root directory clean, put documentation in task folders
- **Follow workflows** - Use the provided workflow documents as guides
- **Save context** - Only process inbox if items actually exist

## Folder Structure

```
ai/
├── AI_README.md    # This file (simple guide)
├── WORKFLOW.md     # Simple workflow steps
├── TODO.md         # Task list (your starting point)
├── inbox/          # Where new ideas go first
│   ├── ideas/      # Simple feature suggestions
│   └── planned/    # Ideas ready to become tasks
├── tasks/          # Task folders (where the work happens)
│   └── TODO-XXX/   # Individual tasks
│       ├── task.md      # Simple step-by-step instructions
│       ├── context.md   # Background (optional)
│       ├── workflow.md  # Implementation steps (optional)
│       ├── notes.md     # Your notes (optional)
│       └── summaries/   # AI completion reports
└── templates/      # Simple templates for new tasks
```

