---
layout: base.njk
title: Home
---

<section class="hero">
  <img src="/apps/fichero/images/icon.png" alt="Fichero Icon" class="hero-icon">
  <h1>Fichero</h1>
  <p class="hero-subtitle">Organize, search, and process your documents with AI — locally on your Mac</p>
  <a href="https://github.com/dtubb/fichero/releases/latest" class="btn">Download for macOS</a>
</section>

## What is Fichero?

Fichero is a native macOS document management app with built-in AI processing. It manages your documents locally using DuckDB and LanceDB, and connects to AI models through LangChain for semantic search, document processing, and automated workflows. The backend runs Python with FastAPI, embedded directly inside the Mac app — no separate server to manage.

"Fichero" is Spanish for a card-file cabinet, recalling the ways academics, researchers, and other knowledge workers have long used filing systems and index cards for their work.

## How It Works

**1. Document Library** — Import, organize, and browse your documents in a native Mac interface. Create folders, add metadata, and manage your collection.

**2. Semantic Search** — Find documents by meaning, not just keywords. Fichero uses vector embeddings to understand what your documents are about and surface relevant results.

**3. AI Processing** — Connect to local models via Ollama or cloud providers. Run workflows to summarize, extract, classify, and transform your documents.

**4. Offline First** — Everything runs on your Mac. Your documents stay local. AI processing works with Ollama when you have no internet connection.

## Download

Version 0.0.1

Fichero runs as a native macOS app. It requires macOS 15.0 (Sequoia) or later.

<a href="https://github.com/dtubb/fichero/releases/latest" class="btn">Download Fichero.dmg</a>

## Release Notes

### 0.0.1

- Document library with folder organization
- File import and metadata management
- Basic search functionality
- Feature flag system for controlled rollout
- Embedded Python backend (FastAPI + DuckDB + LanceDB)
- Sparkle auto-update integration

## About

Fichero is released by Daniel Tubb under the Tubb Lab imprint. Daniel is an Associate Professor of Anthropology at the University of New Brunswick.

<div class="about-links">
  <a href="https://tubblab.com">Tubb Lab</a>
  <a href="https://dtubb.github.io">Daniel Tubb</a>
</div>
