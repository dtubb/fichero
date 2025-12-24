# Backend Key Files

## Essential Files for Development

### Main Entry Points
- `src/fichero/api/main.py` - FastAPI application entry point
- `src/fichero/__init__.py` - Main package initialization

### Core API Routes
- `src/fichero/api/routes/documents.py` - Document management endpoints
- `src/fichero/api/routes/search.py` - Search functionality
- `src/fichero/api/routes/chat.py` - AI chat endpoints
- `src/fichero/api/routes/workflows.py` - Workflow execution

### Data Layer
- `src/fichero/db.py` - Database operations (DuckDB + LanceDB)
- `src/fichero/models.py` - Data models and schemas
- `src/fichero/storage.py` - File storage management

### AI Integration
- `src/fichero/llm.py` - LLM provider integration
- `src/fichero/workflows/` - AI workflow system
  - `builder.py` - Workflow construction
  - `resolver.py` - Workflow execution
  - `registry.py` - Available workflow tools

### Configuration
- `src/fichero/providers.py` - AI provider configurations
- `src/fichero/bookmarks.py` - Bookmark management

## Development Tips

### Finding Files
```bash
# List all Python files
find src/fichero -name "*.py"

# Search for specific functionality
grep -r "search" src/fichero/api/routes/
```

### Understanding Dependencies
```bash
# View imports in a file
grep "^import\|^from" src/fichero/api/main.py

# Find where a module is used
grep -r "from fichero.db import" src/
```

### Code Navigation
- Use `grep` or `rg` (ripgrep) to search across files
- Use `tree` to visualize directory structure
- Use `less` or `bat` to view file contents