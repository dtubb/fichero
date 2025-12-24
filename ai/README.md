# AI Development Guide

## About This Project

I am developing Fichero - a document management and AI processing system for macOS with:
- **Backend**: Python/FastAPI for API services
    - **AI/ML**: LangChain, LangGraph for workflows
    - **Storage**: DuckDB + LanceDB for documents
- **Frontend**: Swift/SwiftUI for macOS application

## Quick Start

1. **Read WORKFLOW.md** for complete development process
2. **Check TODO.md** for tasks
3. **Pick Task**: Always check for `[>]` (in progress) first!
4. **Implement**: Follow workflow in `tasks/TODO-XXX/`

## File Structure

```
ai/
├── README.md          # You are here (quick start)
├── WORKFLOW.md        # Complete workflow reference
├── TODO.md            # Task list with status
├── tasks/TODO-XXX/    # Individual task folders
├── templates/         # Task file templates
└── scripts/           # Automation scripts
```

## Task Status

- `[ ]` Available - Ready for implementation
- `[>]` In Progress - Currently being worked on
- `[x]` Completed - Done (keep in place)

## Creating New Tasks

**Use Script:**
```bash
python scripts/generate_task.py TODO-XXX "Task Name" "Description"
```

## Critical Rules

1. Never work on undefined tasks
2. Always check TODO.md first
3. Follow WORKFLOW.md instructions
4. Update task status when complete

## More Details

See WORKFLOW.md for complete development process.