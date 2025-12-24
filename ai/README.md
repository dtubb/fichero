# AI Development Guide

## About This Project

Fichero is a document management and AI processing system for macOS with:
- **Backend**: Python/FastAPI for API services
  - **AI/ML**: LangChain, LangGraph for workflows
  - **Storage**: DuckDB + LanceDB for documents
- **Frontend**: Swift/SwiftUI for macOS application

**AI's Role**: This AI assistant helps with planning, task management, code implementation, testing, and documentation following the structured workflow defined in this directory.

## Quick Start

1. **Read WORKFLOW.md** for complete development process
2. **Check TODO.md** for available tasks
3. **Pick Task**: Always check for `[>]` (in progress) first!
4. **Implement**: Follow workflow in `tasks/TODO-XXX/`

## Project Context

- **Goal**: Build a document management system with features defined in README.md file
- **Architecture**: Decoupled backend/frontend with AI workflow integration in ai/README.md
- **Current Phase**: Universal navigation and CRUD operations

## File Structure

### Complete Project Structure
```
fichero/
├── .venv/             # Python virtual environment
├── ai/                # AI development workspace (you are here)
│   ├── README.md       # AI development guide
│   ├── WORKFLOW.md     # Development workflow
│   ├── TODO.md         # Task tracking
│   ├── tasks/          # Individual task folders
│   ├── templates/      # Task file templates
│   └── scripts/        # Automation scripts
├── src/               # Python backend source code
│   ├── fichero/        # Main backend package
│   │   ├── api/        # API endpoints
│   │   ├── loaders/    # Data loaders
│   │   ├── models.py   # Data models
│   │   ├── db.py       # Database operations
│   │   └── ...         # Other backend modules
│   └── tests/          # Backend tests
├── Fichero/           # macOS frontend (Swift/SwiftUI)
│   ├── Fichero/        # Main app source
│   ├── FicheroTests/   # Frontend tests
│   └── Fichero.xcodeproj
├── docs/              # Documentation
├── README.md          # Main project README (human-focused)
├── pyproject.toml     # Python project configuration
```

### AI Directory Focus
The `ai/` directory contains the AI development workspace with:
- Task management system
- Development workflows
- Automation scripts
- Task-specific documentation

## Task Status

- `[ ]` Available - Ready for implementation
- `[>]` In Progress - Currently being worked on
- `[x]` Completed - Done (keep in place for reference)

## Creating New Tasks

```bash
# 1. Add task to TODO.md
# Example: echo "- [ ] TODO-016: Implement Search API (P1, Medium)" >> TODO.md

# 2. Create task folder and copy templates
mkdir tasks/TODO-XXX
cp templates/* tasks/TODO-XXX/

# 3. Edit task files (see WORKFLOW.md for details)
```

**See WORKFLOW.md for complete task creation and editing guidelines**

## Critical Rules

1. Never work on undefined tasks
2. Always check TODO.md first
3. Follow WORKFLOW.md instructions
4. Update task status when complete
5. Request human review for complex changes

**Note:** Detailed troubleshooting and contribution guidelines are in WORKFLOW.md