# Fichero Architecture Overview

## Overview

Fichero is a document management and AI processing application for macOS with a SwiftUI frontend and Python backend. It provides hierarchical document storage, semantic search, AI-powered document processing, and a visual workflow editor.

## Architecture Diagram

```
┌─────────────────┐         ┌─────────────────┐        ┌─────────────────┐
│  Swift UI App   │────────▶│  Python API     │        │    LiteLLM      │
│  library/browser│         │  (FastAPI)      │        │(prices/models/  │
│  metadata/search│         └────────┬────────┘        │ provider info)  │
│  chat/workflows │                  │                 └─────────────────┘
│  activity/compare│                 │
└─────────────────┘                  │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
┌───────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ DuckDB+Lance  │          │    LangGraph    │          │    LangChain    │
│ (storage)     │          │   (workflows)   │          │  (llm calls)    │
│               │          │  visual node    │          │                 │
│               │          │    editor       │          │                 │
└───────┬───────┘          └────────┬────────┘          └────────┬────────┘
        │                           │                            │
        ▼                           ▼                            ▼
┌───────────────┐          ┌─────────────────┐          ┌─────────────────┐
│  FastEmbed    │          │  Tool Registry  │          │  LLM Providers  │
│ (embeddings)  │          │ vision/transform│          ├─────────────────┤
└───────────────┘          │ llm/convert     │          │ Local:          │
                           │ logic/conditions│          │  Apple Vision   │
                           └─────────────────┘          │  Ollama/LMStudio│
                                                        │  Hugging Face   │
                                                        ├─────────────────┤
                                                        │ Commercial:     │
                                                        │  OpenAI/Anthropic│
                                                        │  Google/Groq/etc│
                                                        └─────────────────┘
```

## SwiftUI Frontend (Fichero/Fichero/)

### Main Components

1. **FicheroApp.swift** - Main app entry point
   - Manages app state and backend connection
   - Handles menu commands and keyboard shortcuts
   - Coordinates view modes (sidebar, browser, preview, inspector)

2. **ContentView.swift** - Main 3-column layout
   - Sidebar (navigation/search/chat/workflows/activity)
   - Browser (document grid/list/table/map views)
   - Preview/Inspector (document content and metadata)

3. **Services/**
   - **APIClient.swift** - REST API client for Python backend
   - **DocumentService.swift** - Document management
   - **ProviderService.swift** - LLM provider configuration
   - **ChatService.swift** - RAG-based conversation UI
   - **WorkflowService.swift** - Visual workflow editor

4. **Models/**
   - Swift data models matching Python Pydantic models
   - Document hierarchy (collections, folders, files, pages, chunks)
   - Workflow definitions and execution state
   - Provider configurations

5. **Views/**
   - **Sidebar/** - Navigation modes
     - Library browser (hierarchical document tree)
     - Search interface (semantic + keyword)
     - Chat interface (RAG conversations)
     - Workflow editor (visual node canvas)
     - Activity monitor (processing history)
   - **Browser/** - Document views (icons, list, table, map)
   - **Inspector/** - Metadata editor and preview
   - **Workflow/** - Visual node editor with drag-and-drop

### Key Features

- **Universal Navigation**: Multiple sidebar modes (navigate, search, chat, workflows, activity)
- **View Modes**: Icons, list, table, map layouts
- **Preview Toggles**: Independent preview pane controls
- **Provider Management**: Add/configure LLM providers with API keys
- **Model Browser**: Search and filter models by capabilities and pricing
- **Workflow Editor**: Visual node-based pipeline builder

## Python Backend (src/fichero/)

### Core Modules

1. **api/main.py** - FastAPI application
   - REST endpoints for documents, search, chat, workflows, providers
   - CORS configured for local SwiftUI app
   - Health checks and statistics

2. **db.py** - Database Layer (DuckDB + LanceDB)
   - **DuckDB**: Documents, artifacts, workflows, runs
   - **LanceDB**: Vector search embeddings
   - CRUD operations, queries, semantic search
   - Embedding generation with FastEmbed

3. **models.py** - Pydantic data models
   - **Document**: Hierarchical document structure
   - **Artifact**: Processing outputs
   - **Workflow**: Pipeline definitions
   - **Run**: Workflow execution state
   - **Provider**: LLM provider configurations

4. **providers.py** - LLM Provider Catalog
   - Hardcoded provider definitions
   - Local providers: Apple Vision, Ollama, LM Studio
   - Cloud providers: OpenAI, Anthropic, Google, Groq, etc.
   - Provider capabilities (vision, embeddings, streaming)

5. **workflows/** - Workflow Engine
   - **registry.py**: Tool registry with decorators
   - **builder.py**: LangGraph workflow compiler
   - **resolver.py**: Input resolution and conditional logic
   - **types.py**: Workflow data structures
   - **tools/**: Individual tool implementations

6. **llm.py** - LLM Interface
   - LangChain integration
   - Provider abstraction layer
   - Model selection and configuration

7. **ingest.py** - Document Ingestion
   - File loaders (PDF, images, text, docx)
   - Metadata extraction
   - Content processing pipeline

8. **storage.py** - File Storage
   - Library management
   - Thumbnail generation
   - Security-scoped bookmarks

### Workflow System

Fichero uses **LangGraph** for visual workflow editing and execution:

**Workflow Definition** (JSON):
```json
{
  "name": "Catalogue",
  "provider": "openai",
  "model": "gpt-4",
  "nodes": [
    {
      "id": "load",
      "tool": "load_files",
      "inputs": {},
      "config": {}
    },
    {
      "id": "transcribe",
      "tool": "transcribe",
      "inputs": {"files": "$.nodes.load.output"},
      "config": {}
    }
  ],
  "edges": [
    {"source": "load", "target": "transcribe"}
  ]
}
```

**Execution Flow**:
1. SwiftUI sends workflow definition to API
2. Python builds LangGraph StateGraph
3. Nodes execute tools with resolved inputs
4. Results stored in DuckDB
5. Progress updates sent back to SwiftUI

### Tool Registry

Tools are registered with metadata for the visual editor:

```python
@register_tool(
    name="transcribe",
    display_name="Transcribe",
    description="Extract text from images using vision LLM",
    category="vision",
    icon="text.viewfinder",
    color="blue",
    input_ports=[PortDef(id="files", name="Files", data_type=DataType.FILES)],
    output_ports=[PortDef(id="text", name="Text", data_type=DataType.TEXT)],
    uses_llm=True,
)
async def transcribe(state: State, config: dict) -> dict:
    ...
```

### Provider Management

**Provider Types**:
- **Built-in**: Apple Vision, Apple Intelligence (no config)
- **Local**: Ollama, LM Studio (optional server URL)
- **Cloud**: OpenAI, Anthropic, Google, Groq, etc. (API key required)

**Provider Catalog** defines:
- Name, description, icon
- API key requirements
- Capabilities (vision, embeddings, streaming)
- Default models
- Sort order for UI

**User Configuration**:
- API keys stored in macOS Keychain
- Models selected per provider
- Connection testing
- Model browser with filtering

## Data Flow

### Document Ingestion

1. User imports files/folders via SwiftUI
2. SwiftUI calls `POST /api/ingest/file` or `POST /api/ingest/folder`
3. Python processes files through loaders
4. Creates Document hierarchy in DuckDB
5. Generates thumbnails and metadata
6. Returns document IDs to SwiftUI

### Search

1. User enters query in SwiftUI search mode
2. SwiftUI calls `POST /api/search` with query and filters
3. Python:
   - Parses query (semantic + keyword)
   - Searches LanceDB embeddings
   - Returns ranked results with metadata
4. SwiftUI displays results in browser

### Chat (RAG)

1. User asks question in chat interface
2. SwiftUI calls `POST /api/chat` with message and context
3. Python:
   - Retrieves relevant documents from DuckDB
   - Generates embeddings for query
   - Searches LanceDB for similar content
   - Calls LLM with retrieved context
   - Returns response with citations
4. SwiftUI displays response and sources

### Workflow Execution

1. User designs workflow in visual editor
2. SwiftUI calls `POST /api/workflows` with workflow definition
3. Python:
   - Builds LangGraph from definition
   - Executes nodes in order
   - Resolves inputs between nodes
   - Handles conditional branching
   - Stores artifacts in DuckDB
4. SwiftUI shows progress and results

## Key Technologies

### Frontend
- **SwiftUI**: Modern declarative UI framework
- **Combine**: Reactive programming for async operations
- **AppKit**: Native macOS integrations (menus, panels, keychain)

### Backend
- **FastAPI**: REST API framework
- **DuckDB**: Embedded analytical database
- **LanceDB**: Vector search for embeddings
- **LangGraph**: Workflow engine with visual node editor
- **LangChain**: LLM abstraction layer
- **LiteLLM**: Unified LLM provider interface
- **FastEmbed**: Lightweight embedding model

### AI Providers
- **Local**: Apple Vision, Ollama, LM Studio, Hugging Face
- **Cloud**: OpenAI, Anthropic, Google, Groq, Mistral, Cohere
- **Specialized**: DashScope (Qwen), Perplexity (search-augmented)

## Running the Application

### Start the Backend
```bash
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

### Run the Swift App
1. Open `Fichero/Fichero.xcodeproj` in Xcode
2. Select target and run
3. App checks backend health on launch
4. Shows provider setup if no providers configured

### Tests
```bash
PYTHONPATH=src .venv/bin/pytest tests/unit/ --ignore=tests/unit/_archived
```

## Data Model

### Document Hierarchy
```
Collection (archive/project)
├── Folder (box, series)
│   ├── Group (logical document)
│   │   ├── File (image, PDF, audio)
│   │   │   ├── Page (within PDF)
│   │   │   │   ├── Chunk (region/segment)
```

### Core Entities

1. **Document**: Source material with metadata
   - `id`, `parent_id`, `doc_type`, `file_type`
   - `name`, `path`, `page_content`
   - `metadata` (extensible key-value pairs)
   - `status` (pending, processing, completed, failed)

2. **Artifact**: Processing outputs
   - `id`, `document_id`, `artifact_type`
   - `content`, `metadata`, `created_at`

3. **Workflow**: Pipeline definition
   - `id`, `name`, `description`
   - `provider`, `model`, `nodes`, `edges`
   - `created_at`, `updated_at`

4. **Run**: Workflow execution
   - `id`, `workflow_id`, `status`
   - `started_at`, `completed_at`
   - `inputs`, `outputs`, `error`

5. **Provider**: LLM provider configuration
   - `id`, `provider_type`, `name`
   - `api_key_id` (Keychain reference)
   - `api_base`, `models`
   - `is_enabled`, `sort_order`

## Workflow Examples

### Catalogue Workflow
```
[Files] → [Loaders] → [Transcribe] → [Extract Entities]
                                      │
                                      ├── [Timelines]
                                      ├── [Keywords]
                                      ├── [Events]
                                      └── [Summarize]
                                              │
                                              ▼
                                        [Catalogue]
                                              │
                                     ┌────────────────┬───────────────┼───────────────┐
                                     ▼                ▼               ▼               ▼
                               [Save to         [To Word]      [To JSON]      [To PDF]
                                Library]
```

### OCR Workflow
```
[Image Files] → [Apple Vision OCR] → [Language Detection] → [Translate] → [Save Transcription]
```

### Metadata Extraction
```
[PDF Files] → [Extract Text] → [Extract Tables] → [Extract Images] → [Generate Summary]
```

## Architecture Benefits

1. **Separation of Concerns**: Clean separation between UI and backend
2. **Extensibility**: Easy to add new tools and providers
3. **Visual Workflows**: Non-technical users can design processing pipelines
4. **Multi-Provider Support**: Use local or cloud LLMs as needed
5. **Offline Capable**: Local providers work without internet
6. **Performance**: DuckDB + LanceDB for fast local search
7. **Security**: API keys stored in macOS Keychain
8. **Portability**: Library stored in standard macOS locations

## Future Enhancements

- **Collaboration**: Shared libraries and workflows
- **Versioning**: Document and workflow version control
- **Templates**: Pre-built workflow templates
- **Scheduled Jobs**: Automated processing pipelines
- **Export**: Share collections as PDF/Word/JSON
- **Integration**: Plugins for other apps (Devonthink, etc.)
