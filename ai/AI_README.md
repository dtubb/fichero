# AI_README.md

**Fichero**: Document management and AI processing for macOS. Organize, search, chat, and run AI workflows on documents.

You are an autonomous AI agent to help with building Fichero. If you need more context, see README.md.

## Quick Start

### Smart Mode Selection:

**Step 1: Check for inbox items**
```bash
ls ai/inbox/
```
- **If files exist** → Enter Inbox Mode (Option 1)
- **If empty** → Enter Task Mode (Option 2)

**Option 1: Inbox Mode**
1. Follow `ai/workflows/INBOX_WORKFLOW.md` completely. Process only one inbox idea at a timer.
2. Stop when inbox processing is done. 
3. Commit to GitHub, if not alrady commited. Use the template `ai/templates/git_update_template.md`

**Option 2: Task Mode**
1. Follow `ai/workflows/TASK_WORKFLOW.md` completely. Complete only one task.
2. Stop when task is done.
3. Commit to GitHub, if not alrady commited. Use the template `ai/templates/git_update_template.md`

### Key Principles
- **Save context** - Only enter Inbox Mode if items exist
- **One mode at a time** - Complete chosen mode fully
- **Don't switch modes** - Either Inbox Mode OR Task Mode
- **Do Ask human** - When unsure about anything, make best guess based on information you have. Or, add inbox item to research more.

## Rules

- **No emoji** - Use clear text only
- **Small tasks** - Break complex work into simple, focused tasks
- **Clear instructions** - Make task files easy to understand and concise
- **One mode at a time** - Complete Inbox Mode OR Task Mode fully then stop
- **Ask human** - Request input when unsure about anything
- **Clean structure** - Keep root directory clean, put summaries and documentation in task folders
- **Follow workflows** - Use the provided workflow documents as guides
- **Save context** - Only process inbox if items actually exist

## Folder Structure

```
ai/
├── AI_README.md                    # This file (simple guide)
├── TODO.md                         # Task list (your starting point)
├── contexts/                       # Essential system context
│   ├── architecture.md             # High-level system overview
│   ├── backend/                    # Backend development context
│   │   ├── overview.md             # What the backend does and how it works
│   │   ├── key_files.md            # Essential backend files and navigation tips
│   │   ├── development_standards.md # Best practices and testing standards
│   │   └── workflow_checklist.md    # Step-by-step development workflows
│   └── frontend/                   # Frontend development context
│       ├── overview.md             # What the frontend does and how it works
│       ├── key_files.md            # Essential frontend files and navigation tips
│       ├── development_standards.md # Best practices and testing standards
│       └── workflow_checklist.md    # Step-by-step development workflows
├── docs/                          # Documentation
│   └── workflow.md                 # Workflow documentation
├── inbox/                         # Where new ideas go first
│   ├── ideas/                      # Simple feature suggestions
│   └── planned/                    # Ideas ready to become tasks
├── tasks/                         # Task folders (where the work happens)
│   └── TODO-XXX/                   # Individual tasks
│       ├── task.md                 # Simple step-by-step instructions
│       ├── context.md              # Background (optional)
│       ├── workflow.md             # Implementation steps (optional)
│       ├── notes.md                # Your notes (optional)
│       └── summaries/              # AI completion reports
├── templates/                     # Simple templates for new tasks
│   ├── inbox.md                    # Inbox idea template
│   └── todo/                       # Task templates
│       ├── context_template.md     # Context template
│       └── task_template.md        # Task template
└── workflows/                     # Workflow documents
    ├── INBOX_WORKFLOW.md           # Inbox processing workflow
    ├── TASK_WORKFLOW.md            # Task processing workflow
    └── backend.md                  # Backend workflow details
```

