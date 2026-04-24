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

Fichero 0.0.2 is available for early access.

<a href="#" class="btn">Download Fichero 0.0.2</a>

---

## Releases

### 0.0.2 — April 2026

**New** — **Catalogue workflow**: run on any folder to produce a nine-section archival catalogue entry covering people, dates, rivers, legal references, mines, properties, events, keywords, and a summary narrative. **Locked default workflows**: Transcribe and Catalogue ship as built-in presets that auto-update when the app launches — duplicate them to customize; originals stay protected. **Folder inspector**: click a folder in the sidebar to inspect its contents, metadata, and workflow artifacts in the right-hand panel. **Run Workflow from context menu**: right-click any document selection and choose Run Workflow to execute a workflow directly. **Artifact previews**: the Inspector Artifacts tab shows structured previews for catalogue sections (people, dates, rivers, etc.) as readable tables.

**Improved** — PDF preview now includes a zoom toolbar (zoom in/out, fit to window, 100%). PDF pages navigate with horizontal trackpad swipe. Sidebar section headers now show system icons. The AI Providers menu entry now shows an icon. The Activity monitor shows human-readable workflow node names instead of internal IDs.

**Fixed** — Sidebar drag-and-drop routing for files and folders dropped from Finder. Workflow first-click and activity run display. Document inspector showing stale transcription after workflow completion. Catalogue artifacts not appearing after a workflow run.

### 0.0.1 — Initial Release

- Document library with folder organization and file import
- Semantic search via local vector embeddings
- AI workflow engine with visual node editor
- Support for 37+ file types including PDF, Word, images, audio, and video
- Connect to local models (Ollama) or cloud providers (OpenAI, Anthropic, Google, and more)
- Embedded Python backend — no separate server to install or manage

*Full changelog: [CHANGELOG.md on GitHub](https://github.com/dtubb/fichero/blob/main/CHANGELOG.md)*

---

## About

Fichero is made by Daniel Tubb and the [Tubb Lab](https://tubblab.com). Daniel is an Associate Professor of Anthropology at the University of New Brunswick. Fichero grew out of his work processing historical archival documents.

<div class="about-links">
  <a href="https://tubblab.com">Tubb Lab</a>
  <a href="https://dtubb.github.io">Daniel Tubb</a>
</div>
