(AI generated. Not reviewed.)

# Frequently Asked Questions

### What is Fichero?

Fichero is a native Apple document-workbench for researchers. In its current
shipped form, it is primarily a macOS app backed by a local FastAPI engine. It
helps you ingest, organize, search, and process research materials with
repeatable workflows.

### What does "Fichero" mean?

Fichero is Spanish for "card-file cabinet." The name points to research filing
systems, archive catalogues, and index-card ways of working with sources.

### How does it work?

Fichero has a native app and a backend engine. On macOS, the app can launch the
embedded local engine automatically. That engine handles storage, search,
workflows, and knowledge-graph processing; the app is the client on top.

### What kinds of files can it ingest?

The ingest system supports 56 file extensions across images, documents,
word-processing files, ebooks, audio, and video. Text extraction is implemented
for PDFs, word-processing files, text files, and EPUBs.

### What AI models does it support?

Fichero is model-agnostic. The backend talks to providers through LangChain
integrations, and the app includes model-management surfaces. Local options in
the current codebase include Apple Foundation Models, MLX, LM Studio, and
Ollama. Cloud providers include services such as OpenAI, Anthropic, and Google.

### Does it work offline?

Yes, if you use local models. Your library data stays local, and the macOS app
can run against its local engine. Internet access is only needed when you
choose a cloud provider or a remote backend.

### Does it run on iPhone or iPad?

The repository contains iOS and iPadOS targets, but macOS is still the primary
supported surface today.

### What macOS version is required?

Fichero requires macOS 26 Tahoe or later on Apple Silicon.

### Is my data secure?

Your library data is stored locally. If you use local models, processing stays
on your machine. If you use a cloud provider, the content sent to that provider
leaves your machine for that request.

### Where can I report bugs, ask questions, or request features?

Use [GitHub Discussions](https://github.com/dtubb/fichero/discussions) for user
questions and feedback. GitHub Issues are the development backlog.

### Is Fichero free?

Fichero is currently free during alpha development.

### How is Fichero built?

Fichero is developed in the open with AI coding agents under Daniel Tubb's
direction. The repository contains the manager/worker workflow, review gates,
and docs describing that process. See [How It's Built](how-its-built.md).

### What is the relationship between Fichero and Fichero Toolbox?

They are separate apps. Fichero is the document library and workflow app.
Fichero Toolbox is a different project for connecting AI agents to other tools.
