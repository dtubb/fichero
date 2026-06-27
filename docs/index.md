---
hide:
  - navigation
  - toc
---

<!-- PLACEHOLDER: Daniel to rewrite ALL marketing prose on this page in his own
     words. The STRUCTURE is intentional (hero + tagline + CTAs, the READ/THINK/
     WRITE cards, one-engine-many-surfaces, where-to-next) and loosely inspired
     by clean project landing pages like beeware.org — but every sentence of
     copy below is a stand-in pulled from the repo's own README/about.md and
     should be replaced. No external site's wording is reused. -->

# Fichero

<!-- PLACEHOLDER: Daniel to rewrite -->
**A macOS document-management and knowledge-graph studio for researchers.**

<!-- PLACEHOLDER: Daniel to rewrite -->
*Fichero* (Spanish: **file cabinet**, **card index**) gives a researcher's
corpus — PDFs, fieldwork notes, audio, images, transcripts, references — a
single home with semantic understanding. Ask a question and find the relevant
passage, not just the filename.

<!-- PLACEHOLDER: Daniel to rewrite -->
AI here is an **instrument, not an interlocutor**: it surfaces facts and
provenance; it does not interpret for you. Rather than letting an agent decide
how things get done behind the scenes, Fichero lets you build the steps
yourself — visually, repeatably, across a whole corpus — and see what the
machine actually did.

[Get started :material-rocket-launch:](user/getting-started.md){ .md-button .md-button--primary }
[Install Fichero :material-download:](user/install.md){ .md-button }
[Read the docs :material-book-open-variant:](user/README.md){ .md-button }

---

## What Fichero is

<!-- PLACEHOLDER: Daniel to rewrite -->
Fichero is a document library that runs on your Mac, built for working with
primary sources — scanned archives, PDFs, field notes, historical documents,
interview transcripts. You import your sources, read them, extract structured
information from them, annotate them, and write from them. **The whole process
stays on your computer.**

> _Screenshots coming soon — the app ships a four-pane workspace: sidebar,
> content browser, reading area, and a tabbed inspector._

## Three layers of research work

<!-- PLACEHOLDER: Daniel to rewrite the three card descriptions (structure/order is intentional) -->
<div class="grid cards" markdown>

-   :material-magnify-scan: __READ — Hermeneutic layer__

    ---

    Decompose a source into structured facts: entities, claims, dates,
    citations, each anchored to the page it comes from. AI-assisted extraction
    with full provenance — which page, which model, which workflow.

-   :material-lightbulb-on: __THINK — Interpretative layer__

    ---

    Your notes and annotations on a reading: what you observed, what mattered,
    how this source connects to others. Annotation tools, a notes system, and an
    inspector for every document.

-   :material-pencil: __WRITE — Synthesis layer__

    ---

    Write from your sources, with every claim grounded back to where it came
    from in the corpus.

</div>

## One engine, many surfaces

<!-- PLACEHOLDER: Daniel to rewrite (the one-engine-many-surfaces idea + diagram is intentional structure) -->
Fichero is a single backend engine — _"engine is logic; clients are display
surfaces"_ — with thin clients on top: the SwiftUI macOS app, a typed `fichero`
CLI, and an MCP server. All of them talk to the same local FastAPI engine over
pinned, fail-closed HTTPS on `127.0.0.1:8765`, backed by DuckDB + LanceDB,
LangGraph workflows, and 100+ LLM providers.

```text
SwiftUI app ─┐
fichero CLI ─┼─► HTTPS 127.0.0.1:8765 ─► FastAPI engine ─► DuckDB + LanceDB
MCP server ─┘                                           ─► LangGraph workflows
                                                        ─► LLM providers
```

## Where to next

<div class="grid cards" markdown>

-   :material-account: __[User Guide](user/README.md)__

    Install, import, read, search, and run workflows in the Mac app.

-   :material-code-braces: __[Developer Docs](developer/README.md)__

    Architecture, the action registry, the data layer, security, and how to
    contribute.

-   :material-api: __[API Reference](api-reference/index.md)__

    The FastAPI engine's HTTP API, rendered from the live OpenAPI schema.

-   :material-robot-happy: __[How It's Built](agent-workflow/how-fichero-is-built.md)__

    How Fichero is built openly with AI coding agents — the workflow, the
    guardrails, and the review gates.

</div>

---

<!-- PLACEHOLDER: Daniel to rewrite -->
Fichero is model-agnostic and works with open-source models (via Ollama or LM
Studio) as well as commercial providers. It is a work in progress, built
primarily for historians and archivists.
