# Chapter 3. The Fichero Window

*Drafted by AI.*

Fichero's main interface is a single window: a sidebar on the left, the documents of your library in the middle, a reader for the page you are looking at, and an inspector on the right. The AI in Fichero is there to process source material in inspectable ways: it transcribes handwriting, extracts entities and claims, and produces structured artifacts such as catalogues. Its output stays tied to documents, pages, and workflow runs so you can always see where a fact came from. Interpretation is yours.

Everything is anchored to the source. Fichero decomposes a document into structured facts — entities, claims, dates, citations — each tied to the specific page it comes from, and it runs workflows (transcription, entity extraction, catalogue generation, and so on) across your documents. The window is where you watch that happen and check it against the original.

### The Window at a Glance

![The Fichero Window](../images/fichero-window.png)

*Figure: The Fichero Window, with its main interface elements. (A labeled screenshot with numbered callouts is still needed here — see the note at the end of this section.)*

A Fichero window works with one library. Its main elements, numbered as in the figure, are:

1. **Toolbar** — the row of controls across the top: import, the layout picker, running a workflow on your selection, the search field, and the sidebar and inspector toggles. *See [The Toolbar](#the-toolbar) below, and [Appendix C: Keyboard Shortcuts](13-appendix-c-keyboard-shortcuts.md) for the full command list.*
2. **Sidebar** — the navigator that switches the whole window between modes and, in Library mode, shows your library tree and saved searches. *See [The Sidebar and Its Modes](#the-sidebar-and-its-modes) below.*
3. **Library Browser** — the documents and folders of the current view, shown in whichever layout you have chosen. *See [The Library Browser](#the-library-browser) below, and [Managing Your Library](04-managing-your-library.md).*
4. **Reader** — the page, scan, or PDF you are looking at, with its own tabs for the page, its knowledge, and your notes. *See [The Reader](#the-reader) below, and [Reading, Transcribing, and Annotating](05-reading-transcribing-and-annotating.md).*
5. **Inspector** — the panel that shows everything Fichero knows about the selected document: its source text, artifacts, extracted knowledge, and notes. *See [The Inspector](#the-inspector) below, and [The Knowledge Graph](08-the-knowledge-graph.md).*

You can resize each region by dragging the dividers, and hide the sidebar or the inspector (the inspector toggles with ⌃⌘I) when you want more room to read. The window remembers these choices per library, so it opens the way you left it. Each window holds one library; open a second window to work in another library at the same time.

> **Screenshot needed.** This figure should be a screenshot of the Fichero window with callout arrows to elements 1–5 above (Toolbar, Sidebar, Library Browser, Reader, Inspector), in the manner of a standard "user interface elements" figure. Placeholder path: `../images/fichero-window.png`.

### The Toolbar

The toolbar runs across the top of the window and gathers the actions you reach for most:

- **Import** — the add menu: **Link Files…** (⌘I), **Copy Files…** (⌥⌘I), and **Move Files…** (⇧⌘I). *See [Managing Your Library](04-managing-your-library.md).*
- **Layout picker** — switches the Library Browser between Icons, List, Columns, Canvas, and Space (⌘1–⌘5).
- **Run workflow** — runs a workflow on the current selection (⇧⌘R). *See [Workflows](06-workflows.md).*
- **Search field** — full-text and semantic search; results render into the Library Browser. *See [Searching](07-searching.md).*
- **Sidebar and inspector toggles** — show or hide the side panels; the inspector toggle is ⌃⌘I.

### The Sidebar and Its Modes

The sidebar switches the whole window between modes. Each mode reuses the same window layout, so the browser, reader, and inspector stay where you expect them. The modes are:

- **Library** — browse your documents and folders. This is the default, and where you spend most of your time.
- **Search** — a search field and your saved searches; results render into the same document layouts the Library uses, so you can look at a result set as icons, a list, or a table. *See [Searching](07-searching.md).*
- **Chat** — ask questions about your documents in a conversation grounded in library retrieval.
- **Workflows** — build and run the step-by-step processing pipelines. *See [Workflows](06-workflows.md).*
- **Automation** — schedules, triggers, and automated flows.
- **Activity** — watch workflow runs in progress and review finished ones.
- **Research** — research projects and their workspace.
- **Knowledge Graph** — browse the entities and claims extracted across the library. *See [The Knowledge Graph](08-the-knowledge-graph.md).*

You can switch modes from the keyboard with Control-Command and a number — ⌃⌘1 for Library, ⌃⌘2 for Search, ⌃⌘3 for Chat, and so on up the list. Not every mode is enabled in every build: modes that are still settling can be hidden, and the shortcut numbers skip the ones that are turned off, so what you see depends on the release you are running.

Within Library mode, the sidebar shows the library tree and your saved searches; other modes show their own lists (chats, workflows, activity runs).

### The Library Browser

In Library mode, the middle pane shows the documents and folders in the current view. The same set of documents can be shown in five layouts, chosen from the toolbar's layout picker or the **View** menu (⌘1–⌘5):

a. **Icons** (⌘1) — large thumbnails, best for skimming scans and images.
b. **List** (⌘2) — a compact vertical list with small previews.
c. **Columns** (⌘3) — a table of details such as name, type, and dates, in sortable columns.
d. **Canvas** (⌘4) — a freeform two-dimensional surface where you place documents by hand.
e. **Space** (⌘5) — a three-dimensional arrangement of that same canvas.

The richer layouts appear once a library has its advanced views turned on; a plain library may start with Icons alone, and Search with a List. Time- and map-oriented views of your material — a timeline, a geographic map — live in the Knowledge Graph mode rather than here, because they are drawn from the dates and places Fichero has extracted. *See [The Knowledge Graph](08-the-knowledge-graph.md).*

Selection works the way it does in the Finder: click to select one document, hold Shift or Command to select several, and use the selection as the input to other actions such as running a workflow on everything you picked. Right-click any document for a menu of actions; double-click to open it.

### The Reader

When you select a document, the Reader shows it. Page images and scans appear with zoom and a magnifier for fine detail; PDFs open in a page-aware reader with page-by-page navigation. For multi-page material, the Reader and the inspector stay in sync, so the inspector follows the page you are actually viewing. The Reader has three tabs:

a. **Page** — the page itself: the scan, image, or PDF page.
b. **Knowledge** — the entities and claims extracted from the current page.
c. **Notes** — your markings and writing, with two sub-modes: **Marks** for annotations on the page and **Notes** for written notes.

A control on the **View** menu changes how the reading area and its preview pane are arranged. There are three arrangements:

a. **Show Side Preview** — content and preview sit side by side (the widescreen arrangement), giving each the most horizontal room.
b. **Show Bottom Preview** — the preview sits below the content, stacked vertically, so the content keeps the full width.
c. **Hide Preview** — content only, with no preview pane.

The window remembers which arrangement you last chose. Editing tools — non-destructive image and page adjustments — live on the Reader's own toolbar. *See [Reading, Transcribing, and Annotating](05-reading-transcribing-and-annotating.md).*

### The Inspector

The inspector is the panel on the right. Its top icon row switches between four sections; which appear depends on what the selected document has, so the row shows only the ones that apply.

a. **Source** — the document itself: extracted text and page content, plus an **Outline** for drilling down the document’s structure (chapters, sections, pages).
b. **Artifacts** — the outputs that workflows have produced for this document, each with its provenance. *See [Workflows](06-workflows.md).*
c. **Knowledge** — the structured material extracted from the document: entities (people, places, organizations, concepts) and claims (who did what, where, and when). A sub-selector moves between its facets — entities, the graph, and citations — with the curation actions described in [The Knowledge Graph](08-the-knowledge-graph.md).
d. **Notes** — your annotations and free-text research notes, kept separate from the source text; its facets cover notes, annotations, and interpretation. *See [Reading, Transcribing, and Annotating](05-reading-transcribing-and-annotating.md).*

### Settings

Settings is a separate window (⌘,), where you configure Fichero — most importantly, the AI providers and models it can use. You add the providers you want and pick which models each workflow step should use. Because Fichero is model-agnostic, the model picker in a workflow shows only the models you have set up in Settings; if a picker looks empty, open Settings and add a provider first. *See [AI and Privacy](09-ai-and-privacy.md) for what stays on your Mac and what leaves it.*

### Pane Toolbars

Fichero has no single status bar along the bottom of the window. Instead, contextual controls live in small toolbars attached to each pane — the Reader's editing strip, the Library Browser's view controls, the inspector's bottom action strip — so the actions you need sit next to the thing they act on. These appear and change with the pane they belong to.

### The Canvas and Spatial Views

Beyond the list-like layouts, the library can be arranged spatially. The **Canvas** layout is a freeform two-dimensional surface where you place documents by hand — useful for laying out a chapter's sources or sorting a folder visually, the way you would spread papers on a desk. The **Space** layout extends the same idea into three dimensions, rendered with RealityKit. Both are early features; positions are saved per folder, so an arrangement you build stays put when you come back to it.
