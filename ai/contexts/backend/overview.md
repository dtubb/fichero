# Backend Overview

## What Fichero Backend Does

Fichero's Python backend provides:
- **Document Management**: File storage, organization, and metadata handling
- **AI Processing**: Document analysis, transcription, and workflow execution
- **Search**: Full-text and semantic search capabilities
- **REST API**: FastAPI endpoints for the Swift UI to consume

## Architecture

```
Swift UI App → Python FastAPI → DuckDB (structured) + LanceDB (vector search)
```

## Key Components

### Main Entry Point
- `src/fichero/api/main.py` - FastAPI application
- Run with: `uvicorn fichero.api.main:app --reload` or `fichero serve`

### Core Modules
- **API Routes**: `src/fichero/api/routes/` - RESTful endpoints
- **Data Layer**: `src/fichero/db.py`, `src/fichero/models.py` - Database operations
- **AI Integration**: `src/fichero/llm.py`, `src/fichero/workflows/` - AI workflows
- **Storage**: `src/fichero/storage.py` - File management

### Data Storage
- **DuckDB**: Structured document metadata
- **LanceDB**: Vector embeddings for semantic search
- **File System**: Actual document storage

## Development Workflow

### Running the Backend
```bash
# Install dependencies
pip install -e .

# Start development server
fichero serve

# Or directly with uvicorn
uvicorn fichero.api.main:app --reload
```

### Testing
- Unit tests: `tests/unit/` - Fast, isolated component tests
- Integration tests: `tests/integration/` - End-to-end API tests
- Contract tests: `tests/integration/test_api_contracts.py` - API schema validation
- Run tests: `pytest tests/`

### OpenAPI Schema Export

The backend exports its OpenAPI schema for Swift code generation:

```bash
# Export schema (run after API changes)
./scripts/sync_openapi_schema.sh
```

This generates:
- `tests/contracts/openapi.json` - Full OpenAPI 3.0 schema
- `tests/contracts/endpoints.json` - Simplified endpoint list

The Swift frontend uses `swift-openapi-generator` to create type-safe clients from this schema. See `ai/contexts/frontend/api_client.md` for Swift usage.

**Important**: Run the sync script after modifying:
- API routes in `src/fichero/api/routes/`
- Pydantic models in `src/fichero/models.py`
- Request/response schemas

### Key Patterns
- **FastAPI**: RESTful API design with Pydantic models
- **Async/Await**: Non-blocking I/O operations
- **Dependency Injection**: Service-based architecture
- **Error Handling**: Consistent HTTP error responses