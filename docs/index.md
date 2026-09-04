---
hide:
  - navigation
  - toc
---

<p align="center">
  <img src="assets/icon.png" alt="Fichero icon" width="256">
</p>

# Fichero: AI for archives & research

What is Fichero? It's a Mac app to read archives and research material; to transcribe handwritten documents with AI models; to generate structured data from the results; and to navigate and search the results.

**Fichero is in early days. It is open source. It is in Public Alpha. It is not yet in Beta.**

To learn more about how Fichero works, please read the [FAQ](user/guide/10-frequently-asked-questions.md).

<div style="text-align: center" markdown>

[Download Fichero (Public Alpha) :material-apple:](https://github.com/dtubb/fichero/releases/latest/download/Fichero.dmg){ .md-button .md-button--primary }
[Download Fichero Dev :material-flask-outline:](https://github.com/dtubb/fichero/releases/latest/download/Fichero-dev.dmg){ .md-button }
[TestFlight](https://github.com/dtubb/fichero#testflight){ .md-button }

macOS 26+, Apple Silicon.

**Which one?** The **Public Alpha** is Fichero as we recommend it: the
features that have proven themselves — reading, search, markup, workflows,
local and cloud AI models. The **Dev** build is the kitchen sink: every
experimental surface switched on (chat, agents, spatial canvas, unfinished
tools), for people who want to see where Fichero is going and don't mind
sharp edges. Both update themselves; each stays in its own lane.

**Right now: download the Dev build.** The current release's public
download predates the Alpha tier, so today the Dev build is the one with
the full recommended feature set. The next release makes the Public Alpha
the default recommendation again.

--8<-- "docs/_latest.md"

</div>

## Releases

--8<-- "docs/_releases.md"

[Changelog](https://github.com/dtubb/fichero/blob/main/CHANGELOG.md) — the full
commit-level history.

<!-- screenshot slot: hero image of the main window -->
<!-- <p align="center"><img src="assets/screenshot-library.png" alt="Fichero library" width="900"></p> -->

---

<!-- 

## Watch

video slot: short demo embed(s). Keep empty until there is one. -->

---

## Features

Your documents are stored in a library, which can contain folders,
documents, workflows, and saved searches. Fichero can have multiple
libraries open at the same time.

<div class="grid cards" markdown>

-   :material-folder-multiple: __Library__

    ---

    Import and organize your sources; browse them as lists, icons, tables,
    and columns; or extract data and browse them as datasets, timelines,
    and boards; or organize them visually on a 2D or 3D canvas.

-   :material-sitemap: __Workflow bar__

    ---

    Use AI tools and workflows, or chain them together with custom AI
    models per step, to run on a selection — or compare the same steps on
    the same page across models.

-   :material-image: __Preview__

    ---

    A powerful image, PDF, and document viewer: zoom, loupe, and magnify a
    page; show word boxes over the scan; draw and save regions; flip
    between renditions of a page.

-   :material-image-edit: __Edit__

    ---

    Rotate, crop, enhance, and remove backgrounds — as image-editing steps
    you can adjust, reorder, and copy between images.

-   :material-book-open-variant: __Reader__

    ---

    Read transcripts, translations, and other artifacts you write or
    generate, side by side with the original image.

-   :material-chat: __Chat__

    ---

    Ask questions of your sources, scoped to the documents you choose.

-   :material-information: __Inspector__

    ---

    See metadata, artifacts, entities, annotations, and edit history for
    whatever is selected.

-   :material-magnify: __Search__

    ---

    Use semantic search across a whole library, or part of a collection,
    with matches highlighted on the page.

-   :material-pencil: __Markup bar__

    ---

    Select, edit, highlight, and annotate your documents.

</div>

## Under the hood

- **SwiftUI**: A native Mac (and iPhone/iPad) app.
- **FastAPI (Python)**: An embedded server inside the app; the app talks
  to it over a typed, OpenAPI-generated client.
- **DuckDB** and **LanceDB**: Provide the databases behind semantic search.
- **LangChain & LangGraph**: Support model calls and the workflow graphs that  chain transcription, translation, extraction, and cataloguing.
- **Apple Vision & vision LLMs**: Run local on device models, or use cloud models for structured extraction of data using AI models.

More in [How It's Built](user/guide/12-appendix-b-how-fichero-is-built.md)
and the [Contributor Guide](contributor/README.md).

## Documentation

- **[FAQ](user/guide/10-frequently-asked-questions.md)**
- **[User Guide](user/README.md)** for end users.
- **[Contributor Guide](contributor/README.md)** for contributors.

## Open source

Fichero is developed at [github.com/dtubb/fichero](https://github.com/dtubb/fichero). It is coded
(almost) entirely by AI, under the "Creative Direction" of Daniel Tubb, and other [contributors](https://github.com/dtubb/fichero/graphs/contributors). See
[How It's Built](user/guide/12-appendix-b-how-fichero-is-built.md).

Fichero is free and open source, released under the
[GNU Affero General Public License, version 3.0 (AGPL-3.0)](https://www.gnu.org/licenses/agpl-3.0.html).
That means anyone can read the code, use the app, modify it, and share it.
Whoever distributes it, or runs a modified version as a service, must share
their source code under the same license in turn. (Nobody can take Fichero
closed-source). Contributors must agree to a
[Contributor License Agreement](https://github.com/dtubb/fichero/blob/main/CLA.md),
which lets Daniel Tubb, Fichero's maintainer, release Fichero under other
terms (e.g. commercially, or where a channel like Apple's Mac and iOS App Stores has rules where the AGPL do not fit). See
[LICENSING.md](https://github.com/dtubb/fichero/blob/main/LICENSING.md).

---

