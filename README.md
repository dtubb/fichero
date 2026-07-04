# Fichero

*Fichero*, which is Spanish for a filing cabinet or a card index, is an application for Mac, iPhone, and iPad to manage, read, organize, annotate, and process research materials with AI tools. Its audience is researchers with a collection of images of primary sources, historical documents, PDFs of books and articles, hard to read archival materials, handwritten field notes, audio interviews, video recordings, photographs, maps, academic articles, books, and websites. Fichero is both a home for research materials, and a collection of tools to make meaning. 

Fichero lets researchers use AI tools to transcribe, extract metadata, make catalogue entries, and ask questions of their materials, while always being able to easily find the relevant source document or page. 

To do this Fichero uses LamgGraph workflows, which are powered by LLM running locally or remotely. You can build the steps yourself, visually, and then run a workflow across a corpus of material. Fichero lets you use AI as a tool to help with research. It lets anyone use large language models in a programmatic, methodical, step-by-step way over tens or hundreds of thousands of documents. 

Under the hood, Fichero is an app written in SwiftUI. It is a native Mac, iOS, and iPad app. However, it speaks to the Fichero Engine, which is written in Python. The engine uses many of the same Python tools that AI applications rely on: DuckDB, LanceDB, LangChain, LangGraph, oMLX, pi, as well as Apple Intelligence, and Apple Foundation models. 

Fichero is model-agnostic. It works with open-source models as well as
commercial providers, you only need to get yourself an API key. If you have a powerful enough computer you can run models locally. 

AI and machine language tools are incredibly
powerful, and Fichero im here is to make them more navigable and transparent for people.

Fichero is a work in progress. It has been 100% coded by Claude, Codex, and other models over the last two years.

## Installing and using Fichero

Fichero is a Mac, iPad, and iPhone app. It is in a public beta.

**Download** the latest beta for macOS from the
   [releases page](https://github.com/dtubb/fichero/releases/latest).
   
   or
   
   **Install** TestFlight from Apple and request access to the Public Beta of the Mac, iPhone, and iPad app.
   
- **Requirements:** macOS, iOS, or iPad OS 26 Tahoe or later, and an Apple Silicon device.
- [Getting Started](docs/user/getting-started.md): create a library and learn the window.
- [The Interface (Window Tour)](docs/user/interface-tour.md): every major UI element.
- [Importing Documents](docs/user/importing-documents.md), [Reading & Editing](docs/user/reading-and-editing.md), [Search & Knowledge Graph](docs/user/search-knowledge-graph.md), and [AI & Privacy](docs/user/ai-and-privacy.md).

Fichero is Public Beta in active daily development. Keep originals of anything
you import, and treat the app as an experiment.

## Features

- **Library**: Hierarchical document storage with collections
- **Search**: Semantic search via LanceDB embeddings
- **Researcher**: Graph and RAG-based document Q&A, and Agentic access to app via MCP. 
- **Workflows**: Visual node editor for document processing pipelines (LangGraph)
- **Knowledge Graph**: Entities, claims, and relationships extracted from documents (owned by fichero-engine; surfaces render)
- **Ingest**: Comprehensive file ingestion with 37+ supported formats
- **CLI / MCP**: Engine endpoints driven from the terminal (`fichero`) and from MCP-aware agents (`fichero-mcp`)

## Documentation

- **End users**: [`docs/user/`](docs/user/), getting started, importing, reading & editing, search & knowledge graph, AI & privacy. (Published on the docs site.)
- **Developers / contributors**: [`docs/contributor/`](docs/contributor/), architecture overview, setup & contributing, OpenAPI & clients, security model, workflows, the action registry. (Published on the docs site.)

## License

MIT. See [`LICENSE`](LICENSE). Copyright (c) 2025 Daniel Tubb.
