# Fichero System Architecture

## What Fichero Is

**Document management and AI processing for macOS** - Organize, search, chat, and run AI workflows on documents.

## High-Level Architecture

```
┌─────────────────┐         ┌─────────────────┐        ┌─────────────────┐
│  Swift UI App   │────────▶│  Python API     │        │    LiteLLM      │
│  (macOS)        │         │  (FastAPI)      │        │(LLM providers)  │
└─────────────────┘         └────────┬────────┘        └─────────────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │  DuckDB+Lance  │
                           │  (Data Storage)│
                           └─────────────────┘
```

## Component Breakdown

### Swift UI (Frontend)
- **Location**: `Fichero/`
- **Purpose**: User interface for document management and AI workflows
- **Key Features**: Browser, Chat, Workflow Editor, Search, Inspector
- **Tech Stack**: SwiftUI, Combine, @Observable state management

### Python API (Backend)
- **Location**: `src/fichero/`
- **Purpose**: REST API providing document management and AI processing
- **Key Features**: File storage, search, AI workflows, metadata management
- **Tech Stack**: FastAPI, DuckDB, LanceDB, LiteLLM

### Data Storage
- **DuckDB**: Structured document metadata (SQL)
- **LanceDB**: Vector embeddings for semantic search
- **File System**: Actual document storage

## Development Workflow

### Running the Full System

```bash
# Terminal 1: Start Python backend
cd /path/to/fichero
pip install -e .
fichero serve

# Terminal 2: Start Swift UI (via Xcode)
open Fichero/Fichero.xcodeproj
# Build and run in Xcode
```

### Testing

**Backend Testing** (Python):
```bash
pytest tests/unit/          # Unit tests
pytest tests/integration/   # Integration tests
```

**Frontend Testing** (Swift):
```bash
# Build and run in Xcode
open Fichero/Fichero.xcodeproj
# 1. Select the Fichero scheme
# 2. Choose a simulator or device
# 3. Click the Run button (▶) or press Cmd+R

# Run tests in Xcode
# 1. Open Test Navigator (Cmd+6)
# 2. Select test cases
# 3. Click the Run button or press Cmd+U

# SwiftLint for code style
swiftlint
```

## Key Integration Points

### API Endpoints
- `GET /api/v1/documents/` - List documents
- `POST /api/v1/documents/` - Create document
- `GET /api/v1/search/` - Search documents
- `POST /api/v1/workflows/` - Execute workflows

### Data Flow
```
Swift UI → HTTP Request → FastAPI → Database → HTTP Response → Swift UI
```

## Essential Context for AI Development

### What AI Needs to Know
1. **System Purpose**: Document management with AI processing
2. **Architecture**: Swift frontend + Python backend
3. **Key Components**: Where to find core functionality
4. **Development Patterns**: How code is organized and written
5. **Testing Approach**: How to verify changes work

### What AI Doesn't Need
- Every single file and function
- Exhaustive code examples
- Implementation details of non-relevant components
- Historical context or deprecated features

## Workflow Type Architecture

### Design Principles

1. **Tool Registry is Single Source of Truth**
   - Port definitions live in `workflows/registry.py`
   - NodeDef stores tool reference, not port copies
   - Ports enriched from registry at runtime

2. **Minimal Data Storage**
   ```
   NodeDef (stored): {id, tool, position, config, label, enabled}
   NodeDef (runtime): above + {inputPorts, outputPorts} from registry
   ```

3. **Generated Types Over Manual Types**
   - Swift uses `Components.Schemas.*` from OpenAPI generator
   - Avoid manual Swift types that shadow generated ones
   - See `ai/tasks/TODO-125/` and `ai/tasks/TODO-126/`

### Data Flow
```
Python Tool Registry (port definitions)
    ↓
Python API (minimal NodeDef in responses)
    ↓
Swift Generated Types (from OpenAPI spec)
    ↓
SwiftUI Views (use generated types directly)
```

### Key Files
- `src/fichero/workflows/registry.py` - Tool definitions with ports
- `src/fichero/workflows/types.py` - NodeDef, EdgeDef models
- `Fichero/FicheroAPIClient/` - Generated Swift client
- `Fichero/Models/GeneratedTypeExtensions.swift` - Minimal extensions