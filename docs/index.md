---
hide:
  - navigation
  - toc
---

(AI generated. Not reviewed.)

<p align="center">
  <img src="assets/icon.png" alt="Fichero icon" width="128">
</p>

# Fichero

**A filing cabinet for research. Organize, read, search, and process primary
sources — on your own Mac, with the AI models you choose.**

[Download for macOS :material-download:](#download){ .md-button .md-button--primary }
[Get started :material-rocket-launch:](user/getting-started.md){ .md-button }
[Read the FAQ :material-help-circle:](user/faq.md){ .md-button }

*Fichero* is Spanish for a filing cabinet or card index. It is for researchers
working with scanned archives, historical documents, handwritten field notes,
audio interviews, photographs, maps, PDFs of books and articles — the material
that is hard to read and harder to find again. Fichero is both a home for that
material and a set of tools for working with it.

!!! warning "Public Beta"
    Fichero is usable, in-progress software under active development. Keep
    originals of anything you import, and treat each dated build as an
    experiment.

## What it does

<div class="grid cards" markdown>

-   :material-folder-multiple: __Library__

    ---

    Import files or folders — 37 file extensions across images, documents,
    ebooks, audio, and video. Link them in place or copy them in. Read the
    source, the extracted text, and everything derived from it side by side.

-   :material-magnify: __Search__

    ---

    Keyword and semantic search across the whole collection, over the same
    engine the app, the CLI, and the MCP server all talk to.

-   :material-sitemap: __Workflows__

    ---

    Build processing steps visually — transcribe, extract, catalogue,
    summarize — then run them across hundreds of thousands of documents,
    step by step and reproducibly.

-   :material-graph: __Knowledge graph__

    ---

    Extraction produces entities and claims with provenance back to the source
    page. Your corrections persist as rules that later imports obey.

</div>

Not everything is finished. The [feature matrix](user/features.md) lists every
capability with its real status — Live, Beta, In progress, or Planned — derived
from the code rather than from a roadmap.

## Documentation

Three manuals, for three readers:

- **[User manual](user/README.md)** — using Fichero. Install, import, read, search,
  run workflows. Start with [What Fichero Is](user/what-fichero-is.md).
- **[Contributor manual](contributor/README.md)** — building Fichero. Architecture,
  the OpenAPI contract, the action registry, the security model, the release lane.
- **[AI manual](ai/README.md)** — the agents that write most of the code, and the
  rules they work under.

## Why it exists

AI tools are powerful and opaque. Fichero exists to make them navigable: every
transcription, every extracted entity, every claim stays one click from the page
it came from. The goal is not to replace interpretation with a chat box — it is
to make document processing inspectable, repeatable, and tied to the source.

## How it works

One engine, many clients. The **Fichero Engine** is a Python FastAPI service
(DuckDB, LanceDB, LangChain, LangGraph) that owns ingest, storage, search,
workflows, and the knowledge graph. The SwiftUI app, the `fichero` CLI, and the
MCP server are thin clients over its HTTPS surface.

Fichero is **model-agnostic**. Run models locally through Apple Foundation
Models, MLX, Ollama, or LM Studio; or bring your own API key for OpenAI,
Anthropic, Google, OpenRouter, and others. Keys live in the macOS Keychain.

See [How It's Built](user/how-its-built.md) for the whole picture.

## System requirements

- **Mac:** macOS 26 or later, Apple Silicon (M1 or later). The engine is
  embedded in the app — nothing else to install.
- **iPhone / iPad:** iOS or iPadOS 26 or later. These connect to an engine
  running on a Mac; they cannot run one themselves.

---

<h2 id="download">Download</h2>

[Download the latest beta :material-apple:](https://github.com/dtubb/fichero/releases/latest){ .md-button .md-button--primary }

Or join the **TestFlight** public beta for the Mac, iPhone, and iPad app.

Releases are dated, not numbered. Before 1.0, expect rough edges, changing
workflows, and occasional library resets between builds. The app updates itself
through Sparkle.

*[Release notes](https://github.com/dtubb/fichero/blob/main/RELEASE_NOTES.md) — what changed in each build you can download.
[Changelog](https://github.com/dtubb/fichero/blob/main/CHANGELOG.md) — the full day-by-day history.*

---

## About

Fichero is made by [Daniel Tubb](https://tubb.ca), an anthropologist and
Associate Professor of Anthropology at the University of New Brunswick. It grew
out of his own work with historical and archival material.

It is open source under the [MIT license](https://github.com/dtubb/fichero/blob/main/LICENSE),
and has been coded almost entirely by frontier AI models under Daniel's
direction — see [How It's Built](user/how-its-built.md). Issues and pull requests are
welcome on [GitHub](https://github.com/dtubb/fichero); start with the
[contributor docs](contributor/README.md).
