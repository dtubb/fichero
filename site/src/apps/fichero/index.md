---
layout: base.njk
title: Home
---

<section class="hero">
  <img src="/apps/fichero/images/icon.png" alt="Fichero Icon" class="hero-icon">
  <h1>Fichero</h1>
  <p class="hero-subtitle">A document library for researchers — organize, search, and process your materials with AI, entirely on your Mac</p>
  <a href="#download" class="btn">Download for macOS</a>
</section>

## What is Fichero?

Fichero is a native macOS app for managing document collections. It keeps everything local — your files, your database, your AI processing — while connecting to whatever AI models you already use or prefer.

"Fichero" is Spanish for a card-file cabinet. The name recalls the index-card filing systems used by researchers, archivists, and scholars — from Niklas Luhmann's Zettelkasten to the physical card catalogues of archives and libraries. Fichero is built for the same kind of work: accumulating materials, finding connections, and making sense of large collections over time.

## Who It's For

Fichero is designed for researchers, scholars, and anyone who works with large collections of documents. It's especially useful if you:

- Work with archival materials, field notes, interviews, or historical documents
- Need to process scanned PDFs, images, and mixed-format collections
- Want to search your documents by meaning, not just keywords
- Run AI workflows — transcription, extraction, summarization — on batches of files
- Care about keeping your data local and under your control

## What It Does

**Document Library** — Import documents by copying them in or linking to files where they already live. Organize them into folders. Browse by grid, list, or table. Preview PDFs, images, and text files in the app.

**Semantic Search** — Search across your collection by meaning. Fichero uses local vector embeddings to understand what your documents are about, so searching for "land tenure disputes" surfaces relevant documents even if those exact words don't appear.

**AI Workflows** — Build processing pipelines using a visual node editor. Connect steps like transcription, entity extraction, summarization, and classification into workflows that run across your entire collection. Workflows run in the background; the Activity monitor shows what's happening.

**AI Providers** — Connect to local models via Ollama or any cloud provider. Fichero uses LiteLLM to support 100+ providers including OpenAI, Anthropic, and Google. For fully offline use, run Ollama locally.

**Offline First** — Your documents and databases stay on your Mac. AI processing with local models works without an internet connection. Cloud providers are optional.

## System Requirements

- macOS 15.0 Sequoia or later
- Apple Silicon (M1 or later)

---

<h2 id="download">Download</h2>

Fichero 0.0.2 is available for early access.

<a href="#" class="btn">Download Fichero 0.0.2</a>

*Download link coming shortly. [Contact Daniel](mailto:dtubb@me.com) if you'd like early access.*

---

## Releases

### 0.0.2 — April 2026

- PDF preview now includes a zoom toolbar (zoom in/out, fit to window, 100%)
- PDF pages navigate with horizontal trackpad swipe
- Sidebar section headers now show system icons
- AI Providers menu entry now shows an icon
- Activity monitor shows human-readable workflow node names instead of internal IDs
- Fixed sidebar drag-and-drop routing for files and folders dropped from Finder
- Fixed workflow first-click and activity run display

### 0.0.1 — Initial Release

- Document library with folder organization and file import
- Semantic search via local vector embeddings
- AI workflow engine with visual node editor
- Support for 37+ file types including PDF, Word, images, audio, and video
- Connect to local models (Ollama) or cloud providers (OpenAI, Anthropic, Google, and more)
- Embedded Python backend — no separate server to install or manage

---

## About

Fichero is made by Daniel Tubb under the [Tubb Lab](https://tubblab.com) imprint. Daniel is an Associate Professor of Anthropology at the University of New Brunswick. Fichero grew out of his work processing historical archival documents.

<div class="about-links">
  <a href="https://tubblab.com">Tubb Lab</a>
  <a href="https://dtubb.github.io">Daniel Tubb</a>
</div>
