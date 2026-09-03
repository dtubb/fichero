# Fichero

*Fichero*, which is Spanish for a filing cabinet or a card index, is a Mac, iPhone, and iPad app that helps you organize, read, transcribe, annotate, and extract data from research materials with AI tools.  Fichero’s audience is researchers with collections of images from primary sources, historical documents, handwritten field notes, and other hard to read materials, as well as PDFs of books and articles, audio interviews, video recordings, photographs, maps, academic articles, books, and websites. Fichero is both a home for research materials, and a collection of tools to work with them.

Fichero lets you use AI tools to transcribe, extract metadata, make catalogue entries, and chat with and ask questions of your materials, while always being able to easily find the relevant source document or page. You can use and build the processing steps yourself, visually, and then run them across a whole collection of material. Fichero lets you use these workflows in a methodical, step-by-step way over tens or hundreds of thousands of documents. AI and machine language tools are incredibly powerful. Fichero aims to make them more transparent, and useful.

Under the hood, Fichero is an app which has two parts: the front-end, user facing app,  written in SwiftUI; and the back-end server written in Python. Fichero is thus both a fully native Mac, iOS, and iPad app, and an app which uses many of the same Python tools powering AI applications, websites, and services. That is, Fichero is build on FastAPI, DuckDB, LanceDB, LangChain, LangGraph, and many other powerful, open-source tools.  

Fichero is fast, capable, and model-agnostic. It can chain tools and workflows together, powered by local or cloud, closed or open-source models. You can use Apple Foundation models for free, or you can get yourself an API key and use powerful Frontier models from Anthropic, OpenAI, and other providers. (If you have a powerful enough computer you can run even run such models locally, for free using MLX, Ollama, LM Studio, and other comparable endpoints.).

There is an iPad and iPhone version, which lets you connect to your Mac library.

## Features

- **Library**: Hierarchical storage for your documents, organized into collections.
- **Workflows**: A visual editor for building document-processing pipelines: transcribe, extract, catalogue, and more, run across a whole corpus.
- **Search**: Semantic search across everything you've imported.
- **Researcher**: ask questions of your documents and get answers grounded in your own sources.

Fichero’s documentation, while not finished, is in two places. First, a **[User Guide](docs/user/README.md)** for people who want to use Fichero. Second, the **[Contributor Guide](docs/contributor/README.md)** for people (and AI agents) who want to help build it.  AI Coding agents should read [`AGENTS.md`](AGENTS.md). 

Fichero is not finished. It is still in Alpha. The [feature matrix](docs/user/features.md) lists capabilities, with a status.

## Installing and using Fichero

Fichero is in a Public Alpha. This means its really early days, so keep original copies of anything
you import. Treat the app as an experiment: useful to be sure, but also unfinished, and full of bugs. If something doesn't work. Explain why on the project discussion board.

**Download** the latest release for macOS from the
   [releases page](https://github.com/dtubb/fichero/releases/latest).
   
   or
   
   **Install** TestFlight from Apple and request access to the latest release of the Mac, iPhone, and iPad app.
   
- **Requirements:** macOS, iOS, or iPad OS 26 Tahoe or later, and an Apple Silicon device.

## How it is Built?

Fichero has been coded since 2024 almost entirely by AI coding agents, under the "Creative Direction" of Daniel Tubb. [How It's Built](docs/user/how-its-built.md) explains the process. It is a work in progress, and it is open source. If you would like to contribute, start with [CONTRIBUTING.md](CONTRIBUTING.md); 

## License

Fichero is open source under the [GNU AGPL-3.0](LICENSE). It is free to
use, study, modify, and share; anyone who distributes it (or serves a
modified version over a network) must share their source the same way.
Official builds for channels whose rules the AGPL does not fit (such as
the Mac App Store) are released by Daniel Tubb under separate terms. See [LICENSING.md](LICENSING.md).
