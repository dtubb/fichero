---
hide:
  - navigation
  - toc
---

<!-- Landing copy salvaged from the previous 11ty site (Daniel's own words).
     Adapted to MkDocs/Material. Release-specific bits (version string, download
     link, release notes) are marked PLACEHOLDER; update them each release. -->

<p align="center">
  <img src="assets/icon.png" alt="Fichero icon" width="128">
</p>

# Fichero

**A document library to organize, search, and process research materials using
workflows, entirely on your Mac.**

[Download for macOS :material-download:](#download){ .md-button .md-button--primary }
[Read the FAQ :material-help-circle:](faq.md){ .md-button }
[Get started :material-rocket-launch:](user/getting-started.md){ .md-button }

Fichero turns scanned archives, PDFs, field notes, and historical documents into
a searchable research library, using visual AI workflows you build yourself. To
learn more about how Fichero works, read the [FAQ](faq.md). Fichero is available
as a free Alpha download.

!!! warning "This is Alpha software"
    Fichero is in active daily development. Things will change. Things will
    break. Don't put irreplaceable work in it yet. Keep originals elsewhere,
    and treat each release as an experiment.

!!! note "Fichero is written by AI coding agents"
    Daniel is an anthropologist, not a software engineer. He directs AI coding
    agents that do the writing: a manager agent orchestrates worker agents, each
    in its own workspace, with build and test gating before anything merges.
    Daniel reviews the result and judges every release by using the app. See
    [How It's Built](how-its-built.md) and the
    [FAQ](faq.md#how-is-fichero-built) for what that looks like in practice.

## What is Fichero?

"Fichero" is Spanish for a card-file cabinet. The name recalls the index-card
filing systems used by researchers, archivists, and scholars, from Niklas
Luhmann's Zettelkasten to the physical card catalogues of archives and
libraries, to the field notes ethnographers write, to Walter Benjamin's
*Arcades Project*.

Fichero is a work in progress. It gives you a visual way to use AI on your
documents.

It's an app that lets you use machine-learning techniques and prompts in a
repeatable, programmatic way. I've built it to do transcription of handwritten
documents using vision language models, to extract named entities, and to
produce catalogues, though the approach could be used for other tasks.

The basic idea: an AI that does things on its own controls how they are done, in
ways that are harder to understand. Fichero instead lets you, the user, visually
build these steps yourself, and connect them together. The Fichero app talks to
fichero-engine, a server that does the processing and storage. It comes with a
powerful database, a vector database, a knowledge graph, and an ontological
layer, so it can be extended in new directions.

Under the hood, fichero-engine connects to a DuckDB database. It talks to model
providers through LangChain, and runs workflows with LangGraph.

## Who it's for

I've written Fichero primarily for anthropologists, historians, and archivists.
Ultimately it's a tool to experiment with using large language models in a
programmatic, methodological, step-by-step way.

It is a desktop app, built on SwiftUI. It is useful to:

- Work with archival materials, field notes, interviews, or historical documents;
- Process scanned PDFs, images, and mixed-format collections;
- Search your documents by meaning as well as keywords;
- Run AI workflows (transcription, extraction, summarization) on batches of files;
- Care about keeping your data local and under your control.

## Model agnostic

Fichero is model agnostic. It works with open-source models as well as
commercial providers; you just get yourself an API key. If you want to run
models locally, you can do so with Ollama or LM Studio.

## Beyond chat, beyond agents

The aim of Fichero is to move beyond the chat interface, and beyond the agentic
model as a black box. Fichero's aim is to give you more control and insight into
how AI does its work.

Fichero gives you tools to use agents to do work in a systematic way, and to
reproduce steps across multiple documents.

AIs are incredibly powerful. Fichero aims to make them more navigable, more
transparent, and more accessible as tools for research. Currently, agents are
not transparent; they are invisible to the user, hidden away on a server, so
it's hard to know what's going on under the covers. With Fichero, the
aim is to be more transparent, and therefore more accessible.

Fichero is a work in progress. Iterative. It is, I hope, something useful.

## What it does

<div class="grid cards" markdown>

-   :material-folder-multiple: __Document Library__

    ---

    Import documents by copying, moving, or linking to files. Organize them into
    folders. Preview PDFs, images, audio, video, and text files in the app.

-   :material-magnify: __Semantic Search__

    ---

    Search across your collection by meaning. Local vector embeddings understand
    what your documents are about, so searching for "land tenure disputes"
    surfaces relevant documents even if those exact words don't appear.

-   :material-sitemap: __Workflows__

    ---

    Build workflows using a visual node editor. Connect steps like transcription,
    entity extraction, summarization, and classification into workflows that run
    across your entire collection.

</div>

## System requirements

- macOS 26 Tahoe or later
- Apple Silicon (M1 or later)

---

<h2 id="download">Download</h2>

<!-- PLACEHOLDER: update the version string + release notes each release. -->
The latest Alpha release is **Fichero 2026.04.29 Alpha**.

[Download the latest Alpha :material-apple:](https://github.com/dtubb/fichero-releases/releases/latest){ .md-button .md-button--primary }

Releases are dated by ship date (calendar versioning). Versions before 1.0 are
Alpha, so features change, bugs happen, and you should expect rough edges.

Until Fichero hits version 1.0:

- **Treat every Alpha as an experiment.** Keep originals of any documents you
  import. The library can be wiped between releases.
- **Things will change.** Workflows, default settings, and UI conventions are
  still being figured out.
- **No telemetry, no analytics.** Fichero doesn't phone home. The only network
  calls are the AI provider you chose (or none, if you use Apple Vision + Apple
  Intelligence).

*Full release notes: [RELEASE_NOTES.md on GitHub](https://github.com/dtubb/fichero/blob/main/RELEASE_NOTES.md)*

---

## About

Fichero is made by Daniel Tubb and the [Tubb Lab](https://tubblab.com). Daniel is
an Associate Professor of Anthropology at the University of New Brunswick.
Fichero grew out of his work processing historical archival documents.

[Tubb Lab](https://tubblab.com) ·
[Daniel Tubb](https://dtubb.github.io)
