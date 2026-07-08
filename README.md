# Fichero

*Fichero*, which is Spanish for a filing cabinet or a card index, is a Mac, iPhone, and  iPad app that helps you manage, read, organize, annotate, and process research materials with AI tools. 

Fichero's audience is researchers with collections of images from primary sources, historical documents, handwritten field notes, and other hard to read materials, as well as PDFs of books and articles, audio interviews, video recordings, photographs, maps, academic articles, books, and websites. Fichero is both a home for research materials, and a  collection of tools work with them.

Fichero lets you use AI tools to transcribe, extract metadata, make catalogue entries, and chat with and ask questions of your materials, while always being able to easily find the relevant source document or page. You can use and build the processing steps yourself, visually, and then run them across a whole collection of material. Fichero lets you use these workflows in a methodical, step-by-step way over tens or hundreds of thousands of documents

AI and machine language tools are incredibly powerful, and Fichero im here is to make them more navigable and transparent for people.


Under the hood, Fichero is an app written in SwiftUI and Python. It is both a native Mac, iOS, and iPad app. It is powered by Fichero Engine, which is written in Python. The engine uses many of the same Python tools that many AI applications, websites, and services rely on: DuckDB, LanceDB, LangChain, LangGraph. 

Fichero is model-agnostic. It works with open-source models as well as
commercial providers, you only need to get yourself an API key. If you have a powerful enough computer you can run models locally. It can conenct to Apple Intelligence and and Apple Foundation models, to run AI models locally. It can also connect to local providers (e.g., oMLX, Ollama, and LMStudo), as well as commercial ones (OpenRouter, Claude, Codex, Gemini, and others.)

The iPad and iPhone version require a Mac to connect to.

Documentation is in three guides: the **[User Guide](docs/user/README.md)** for
using Fichero, the **[Developer Guide](docs/contributor/README.md)** for building
it, and the **[AI Guide](docs/ai/README.md)** for the agents that write most of the
code. Not everything is finished — the [feature matrix](docs/user/features.md)
lists every capability with its real status.

## Features

- **Library** — hierarchical storage for your documents, organized into collections.
- **Search** — semantic search across everything you've imported.
- **Researcher** — ask questions of your documents and get answers grounded in your own sources.
- **Workflows** — a visual editor for building document-processing pipelines: transcribe, extract, catalogue, and more, run across a whole corpus.
- **Knowledge Graph** — entities, claims, and relationships surfaced from your documents.

## Installing and using Fichero

Fichero is in a public beta. It is early days. Keep originals of anything
you import, and treat the app as an experiment.

**Download** the latest beta for macOS from the
   [releases page](https://github.com/dtubb/fichero/releases/latest).
   
   or
   
   **Install** TestFlight from Apple and request access to the Public Beta of the Mac, iPhone, and iPad app.
   
- **Requirements:** macOS, iOS, or iPad OS 26 Tahoe or later, and an Apple Silicon device.

## How it is Built?

Fichero has been coded over the last two years almost entirely by Claude, Codex, Glm 5.2, and other Frontier AI models. It is a work in progress, and it is open source. If you would like to contribute, start with the [Developer Guide](docs/contributor/README.md) and [CONTRIBUTING.md](CONTRIBUTING.md); [How It's Built](docs/user/how-its-built.md) explains the process.

## License

MIT. See [`LICENSE`](LICENSE). Copyright (c) 2025 Daniel Tubb.