---
layout: base.njk
title: Home
---

<section class="hero">
  <img src="/apps/fichero/images/icon.png" alt="Fichero Icon" class="hero-icon">
  <h1>Fichero</h1>
  <p class="hero-subtitle">A document library to organize, search, and process research materials using workflows, entirely on your Mac</p>
  <a href="#download" class="btn">Download for macOS</a>
</section>

> **⚠️ This is Alpha software.** Fichero is in active daily development. Things will change. Things will break. Don't put irreplaceable work in it yet — keep originals elsewhere, treat each release as an experiment. If you find a bug, please file it on [GitHub Issues](https://github.com/dtubb/fichero/issues) so it can be fixed.

> **🤖 Fichero is 100% vibe-coded.** Every line was written conversationally with Claude — Daniel describes what he wants, an AI implements it, they iterate in real time. There's no traditional engineering team. [Read more about how it's done →](/apps/fichero/how-its-made/)

## What is Fichero?

"Fichero" is Spanish for a card-file cabinet. The name recalls the index-card filing systems used by researchers, archivists, and scholars — from Niklas Luhmann's Zettelkasten to the physical card catalogues of archives and libraries, to the field notes ethnographers write, to Walter Benjamin's *Arcades Project*.

Fichero is a work in progress. It gives you a visual way to use AI on your documents.

It's an app that lets you use machine-learning techniques and prompts in a repeatable, programmatic way. I've built it to do transcription of handwritten documents using vision language models, and to extract named entities — but the approach could be used for other tasks.

The basic idea: rather than have an AI do things — where it controls how things are done, in ways that are harder to understand — Fichero lets you, the user, visually build these steps yourself, and connect them together. Fichero is built on a Python backend, with a powerful database, a vector database, a knowledge graph, and an ontological layer, so it can be extended in new directions.

Under the hood, Fichero is a FastAPI server connecting to a DuckDB database. It uses LLMs to check presses, and LangGraph to run models.

## Who It's For

I've written Fichero primarily for anthropologists, historians, and archivists — but it's a tool, ultimately, to experiment with using large language models in a programmatic, methodological, step-by-step way.

It is a desktop app, built on SwiftUI. It is useful to:

- Work with archival materials, field notes, interviews, or historical documents;
- Process scanned PDFs, images, and mixed-format collections;
- Search your documents by meaning, not just keywords;
- Run AI workflows — transcription, extraction, summarization — on batches of files;
- Care about keeping your data local and under your control.

## Model Agnostic

Fichero is model agnostic. It works with open-source models as well as commercial providers — you just get yourself an API key. If you want to run models locally, you can do so with Ollama or LM Studio.

## Beyond Chat, Beyond Agents

The aim of Fichero is to move beyond the chat interface, and beyond the agentic model as a black box. Fichero's aim is to give you more control and insight into how AI does its work.

Fichero gives you tools to use agents to do work in a systematic way, and to reproduce steps across multiple documents.

AIs are incredibly powerful. Fichero aims to make them more navigable, more transparent, and more accessible as tools for research. Currently, agents are not transparent — they are invisible to the user, hidden in a database or a backend, so it's hard to know what's going on under the covers. With Fichero, the aim is to be more transparent, and therefore more accessible.

Fichero is a work in progress. Iterative. It is, I hope, something useful.

## What It Does

**Document Library** — Import documents by copying, moving, or linking to files. Organize them into folders. Preview PDFs, images, audio, video, and text files in the app.

**Semantic Search** — Search across your collection by meaning. Fichero uses local vector embeddings to understand what your documents are about, so searching for "land tenure disputes" surfaces relevant documents even if those exact words don't appear.

**Workflows** — Build workflows using a visual node editor. Connect steps like transcription, entity extraction, summarization, and classification into workflows that run across your entire collection.

## System Requirements

- macOS 15.0 Sequoia or later
- Apple Silicon (M1 or later)

---

<h2 id="download">Download</h2>

The latest Alpha release is **Fichero 2026.04.29 Alpha**.

<a href="#" class="btn">Download Fichero 2026.04.29 Alpha</a>

Releases are dated by ship date (calendar versioning). Versions before 1.0 are Alpha — features change, bugs happen, expect rough edges. See the [download notes](#download-notes) below.

---

## Releases

### 2026.04.29 — Alpha

**New — Knowledge Graph layer.** Catalogue workflows now write structured entity rows (people, places, organizations, events, dates, keywords) into a queryable knowledge graph alongside the human-readable artifact. Same data, two views: the markdown for reading, the typed graph for searching, cross-referencing, and future cross-document navigation. Each claim carries page-level provenance — every entity row knows which page of which document it came from.

**New — Four catalogue workflows out of the box.** *Catalogue* runs the full nine-section archival entry in one cloud LLM pass. *Catalogue (composable)* fans the work out across six per-section extractors (people / places / organizations / events / dates / keywords) so you can swap or customize any one. *Catalogue (Apple Intelligence)* runs the same pipeline entirely on-device using Apple's Foundation Models — zero cloud calls, no API quota, full privacy. Plus two Transcribe variants: *Transcribe (Apple Vision)* (on-device OCR) and *Transcribe* (cloud vision LLM, better for handwriting and historical scripts).

**New — Per-page entity extraction.** When a workflow processes multi-page documents, each page is extracted separately and each extracted entity carries its source page label. The substrate is ready for cross-document views ("show me every page that mentions María Angel") in upcoming releases.

**Improved — Workflow Library.** Folder grouping in the list (Transcribe, Catalogue), generic extractors by default (archive-specific extractors like rivers, mines, properties remain available as draggable tools, but no longer ship in the default workflow), and proper SF Symbol icons for every node on the canvas instead of generic gears.

**Improved — Settings.** Defaults model picker reads from configured providers; folder inspector when nothing is selected; thumbnail aspect ratios respect document orientation in the grid.

**Fixed** — Workflow Library list endpoint returning empty after Reset Defaults. Workflow templates duplicating on every install. Catalogue (composable) reducer running a duplicate extraction pass instead of consuming claims. Several inspector and sidebar bugs from 0.0.1.

### 2026.04.01 — Alpha (initial release)

- Document library with folder organization and file import
- Semantic search via local vector embeddings
- AI workflow engine with visual node editor
- Support for 37+ file types including PDF, Word, images, audio, and video
- Connect to local models (Ollama) or cloud providers (OpenAI, Anthropic, Google, and more)
- Embedded Python backend — no separate server to install or manage

*Full changelog: [CHANGELOG.md on GitHub](https://github.com/dtubb/fichero/blob/main/CHANGELOG.md)*

---

<h3 id="download-notes">Download notes</h3>

Versions are dated by ship day (e.g. `2026.04.29` shipped April 29, 2026). Until Fichero hits version 1.0:

- **Treat every Alpha as an experiment.** Keep originals of any documents you import. The library can be wiped between releases.
- **Things will change.** Workflows, default settings, and UI conventions are still being figured out. A workflow you saved this week may need re-running next week.
- **Bug reports are welcome.** File on [GitHub Issues](https://github.com/dtubb/fichero/issues) — include what you were doing and what happened. The author reads them all.
- **No telemetry, no analytics.** Fichero doesn't phone home. The only network calls are the AI provider you chose (or none, if you use Apple Vision + Apple Intelligence).

---

## About

Fichero is made by Daniel Tubb and the [Tubb Lab](https://tubblab.com). Daniel is an Associate Professor of Anthropology at the University of New Brunswick. Fichero grew out of his work processing historical archival documents.

<div class="about-links">
  <a href="https://tubblab.com">Tubb Lab</a>
  <a href="https://dtubb.github.io">Daniel Tubb</a>
</div>
