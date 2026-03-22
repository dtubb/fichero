---
layout: base.njk
title: FAQ
---

# Frequently Asked Questions

### What is Fichero?

Fichero is a native macOS document management app with built-in AI processing. It lets you organize, search, and process your documents using local or cloud AI models, all from a single Mac app.

### What does "Fichero" mean?

Fichero is Spanish for "card-file cabinet" — the physical index card filing system used by researchers, archivists, and notably by Niklas Luhmann in his Zettelkasten method. The name references both the archival tradition and Fichero's roots in processing historical archival images.

### How does it work?

Fichero is two apps in one: a native SwiftUI frontend for browsing and managing your documents, and a Python FastAPI backend that handles AI processing, search, and data storage. The backend is embedded inside the Mac app and starts automatically — you never need to think about it.

### What AI models does it support?

Fichero connects to AI models through LangChain and LiteLLM, which means it supports 100+ providers including OpenAI, Anthropic, Google, Ollama (local), and many more. For offline use, connect to Ollama and run models entirely on your Mac.

### Does it work offline?

Yes. Fichero is designed for offline-first use. Your documents are stored locally in DuckDB and LanceDB. When connected to Ollama, all AI processing happens on your machine with no internet required.

### What macOS version is required?

Fichero requires macOS 15.0 (Sequoia) or later.

### Is my data secure?

Fichero runs entirely on your Mac. Your documents and databases stay local. AI processing with Ollama happens on-device. When using cloud AI providers, only the content you explicitly send for processing leaves your machine.

### Where can I report bugs or request features?

Please open an issue on the [GitHub repository](https://github.com/dtubb/fichero/issues).

### Is Fichero free?

Fichero is currently free during early development. Pricing for future versions has not been determined.

### What is the relationship between Fichero and Fichero Toolbox?

They are separate apps. Fichero manages documents with AI processing. [Fichero Toolbox](/apps/fichero-toolbox/) connects AI agents to Tinderbox and other Mac apps via MCP. Both are built by Daniel Tubb.
