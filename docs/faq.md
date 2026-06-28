# Frequently Asked Questions

### What is Fichero?

Fichero is a work in progress. At its core, it's an app that lets you use cutting-edge machine-learning techniques and prompts in a repeatable, programmatic way on documents. Rather than have an AI control how things are done in ways that are hard to understand, Fichero gives you a way to visually build the steps yourself, and then reproduce them across your collection.

### What does "Fichero" mean?

Fichero is Spanish for "card-file cabinet," the physical index card filing system used by researchers, archivists, and notably by Niklas Luhmann in his Zettelkasten method. The name references both the archival tradition and Fichero's roots in processing historical archival images.

### How does it work?

Fichero has two parts: the Fichero app, a native SwiftUI app for browsing and managing your documents, and fichero-engine, a server that handles AI processing, search, and data storage. fichero-engine is embedded inside the app and starts automatically, so you never need to think about it.

### What AI models does it support?

Many. Fichero is model-agnostic and you pick the provider per workflow. AI calls go through LangChain provider integrations (LiteLLM is used only for model discovery and cost estimates, not for routing). Local, on-device options include Apple Foundation Models (Apple Intelligence), MLX, LM Studio, and Ollama. Cloud options include OpenAI, Anthropic, and Google. Run everything locally, or bring your own cloud API key, or mix the two.

### Does it work offline?

Yes. Fichero is designed for offline-first use. Your documents are stored locally in DuckDB and LanceDB. With a local provider (Apple Foundation Models, MLX, LM Studio, or Ollama), all AI processing happens on your machine with no internet required.

### What macOS version is required?

Fichero requires macOS 26 (Tahoe) or later.

### Is my data secure?

Fichero runs entirely on your Mac. Your documents and databases stay local. With a local provider (Apple Foundation Models, MLX, LM Studio, or Ollama), AI processing happens on-device. When using cloud AI providers, only the content you explicitly send for processing leaves your machine.

### Where can I report bugs, ask questions, or request features?

For questions, feedback, and feature ideas, use [GitHub Discussions](https://github.com/dtubb/fichero/discussions). That is the place for users to reach the project.

GitHub Issues is the development backlog, where the AI coding agents track their work. It is not a user support channel, so start in Discussions and the team will open an issue if your report needs one.

### Is Fichero free?

Fichero is currently free during early development. Pricing for future versions has not been determined.

### How is Fichero built?

Fichero is written by AI coding agents that Daniel directs. Daniel is an anthropologist, not a software engineer, so he does not write Swift or Python from scratch. He describes what he wants in plain language and decides what to build next, what is broken, and what ships.

The work runs through a manager agent that orchestrates worker agents, each in its own isolated git worktree. A worker implements a GitHub issue, then the change is build-tested and gated before it merges. Daniel reviews the result and judges every release by using the app himself. See [How It's Built](how-its-built.md) for the full picture.

### What is the relationship between Fichero and Fichero Toolbox?

They are separate apps. Fichero manages documents with AI processing. Fichero Toolbox connects AI agents to Tinderbox and other Mac apps via MCP. Both are built by Daniel Tubb.
