# Frequently Asked Questions

### What is Fichero?

Fichero is a work in progress. At its core, it's an app that lets you use cutting-edge machine-learning techniques and prompts in a repeatable, programmatic way on documents. Rather than have an AI control how things are done in ways that are hard to understand, Fichero gives you a way to visually build the steps yourself, and then reproduce them across your collection.

### What does "Fichero" mean?

Fichero is Spanish for "card-file cabinet," the physical index card filing system used by researchers, archivists, and notably by Niklas Luhmann in his Zettelkasten method. The name references both the archival tradition and Fichero's roots in processing historical archival images.

### How does it work?

Fichero has two parts: the Fichero app, a native SwiftUI app for browsing and managing your documents, and fichero-engine, a server that handles AI processing, search, and data storage. fichero-engine is embedded inside the app and starts automatically, so you never need to think about it.

### What AI models does it support?

Fichero connects to AI models through LangChain and LiteLLM, which means it supports 100+ providers including OpenAI, Anthropic, Google, Ollama (local), and many more. For offline use, connect to Ollama and run models entirely on your Mac.

### Does it work offline?

Yes. Fichero is designed for offline-first use. Your documents are stored locally in DuckDB and LanceDB. When connected to Ollama, all AI processing happens on your machine with no internet required.

### What macOS version is required?

Fichero requires macOS 26 (Tahoe) or later.

### Is my data secure?

Fichero runs entirely on your Mac. Your documents and databases stay local. AI processing with Ollama happens on-device. When using cloud AI providers, only the content you explicitly send for processing leaves your machine.

### Where can I report bugs or request features?

Please open an issue on the [GitHub repository](https://github.com/dtubb/fichero/issues).

### Is Fichero free?

Fichero is currently free during early development. Pricing for future versions has not been determined.

### How is Fichero built?

Fichero is vibe-coded. Daniel is an anthropologist rather than a software engineer, and he doesn't write Swift or Python from scratch. Instead, he sits down with [Claude](https://www.anthropic.com/claude) (Anthropic's AI assistant) and describes what he wants in plain language. Claude does the typing; Daniel directs: what the app should do, where it's broken, what to work on next. Sessions are conversational and long, and code, tests, and commits all come out the other end.

### What is the relationship between Fichero and Fichero Toolbox?

They are separate apps. Fichero manages documents with AI processing. Fichero Toolbox connects AI agents to Tinderbox and other Mac apps via MCP. Both are built by Daniel Tubb.
