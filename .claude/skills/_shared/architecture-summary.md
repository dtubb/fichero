# Fichero Architecture Summary (Shared Context for Team Agents)

## What Fichero Is

A macOS document management app with AI processing: document organization, search, RAG chat, visual workflow editor, 37+ file type ingestion, 100+ LLM providers.

## Two-Part System

- **fichero-swiftui/** -- Pure SwiftUI native macOS frontend (189 Swift files)
- **fichero-api/** -- Python FastAPI backend (DuckDB + LanceDB + LangGraph)
- **Bridge:** OpenAPI-generated type-safe Swift client, schema in `fichero-api/tests/contracts/openapi.json`

## Runtime

```
SwiftUI App -> HTTP localhost:8765 -> FastAPI -> DuckDB/LanceDB + LangGraph + LiteLLM
```

## Key Constraints

- Pure SwiftUI, NO AppKit
- Backend MUST run on port 8765
- PYTHONPATH=fichero-api/src for all Python commands
- Generated files are read-only (*Generated.swift, openapi.json, fichero-api-client/)
- SwiftLint zero warnings before commit
- File size: <400 lines recommended, <1000 hard limit
- Conventional commits: fix:, feat:, style:, test:, docs:, chore:, refactor:

## Branch

`codex/restructure-api-swiftui` -- active development branch, 43+ commits ahead of main.
