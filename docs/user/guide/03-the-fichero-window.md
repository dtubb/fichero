# Chapter 3. The Fichero Window


### About the Window

A Fichero window works with one library. It has four main regions, left to right:

1.  
2.  
3.  
4.  

**Sidebar** — the navigator that switches the window between modes.**Library browser** — the documents and folders in the current view.**Reader** — the page, scan, or PDF you are looking at.**Inspector** — the panel that shows everything Fichero knows about the selected document.You can resize each region by dragging the dividers, and you can hide the sidebar or the inspector when you want more room to read. Each window holds one library; open a second window to work in another library at the same time.

### The Sidebar and Its Modes

The sidebar switches the whole window between modes. Each mode reuses the same window layout, so the browser, reader, and inspector stay where you expect them. The modes are:

- 
- 
- 
- 
- 
- 
- 

**Library** — browse your documents and folders. This is the default, and where you spend most of your time. Searching also happens here: search results render into the Library view.**Chat** — ask questions about your documents in a conversation grounded in library retrieval.**Workflows** — build and run the step-by-step processing pipelines.**Automation** — schedules, triggers, and automated flows.**Activity** — watch workflow runs in progress and review finished ones.**Research** — knowledge-graph-backed research questions and answers.**Knowledge Graph** — browse the entities and claims extracted across the library.Not every mode is enabled in every build — alpha releases may hide modes that are still settling.

Within Library mode, the sidebar shows the library tree and your saved searches; other modes show their own lists (chats, workflows, activity runs).

You can switch sidebar modes from the keyboard with Control-Command plus a number key — for example, ⌃⌘1 for Library.

### The Library Browser

In Library mode, the middle pane shows the documents and folders in the current view. The same set of documents can be shown in eleven layouts, chosen from the toolbar:

- 
- 
- 
- 
- 
- 
- 
- 
- 
- 
- 

**Icons** — large thumbnails, best for skimming scans and images.**List** — a compact vertical list with small previews.**Table** — columns of details such as name, type, and dates, with sortable headers.**Columns** — Miller columns, drilling folder by folder as in the Finder.**Grid** — a dense grid of items.**Cards** — larger cards with more metadata per item.**Timeline** — documents arranged along a time axis.**Calendar** — documents placed on a calendar.**Geographic Map** — pins for documents that carry a place, useful for fieldwork material.**Canvas** — a freeform two-dimensional arrangement.**Space** — a three-dimensional spatial view.Selection works the way it does in the Finder: click to select one document, hold Shift or Command to select several, and use the selection as the input to other actions such as running a workflow on everything you picked. Right-click any document for a menu of actions; double-click to open it.

### The Reader

When you select a document, the Reader shows it. Page images and scans appear with zoom and a magnifier for fine detail; PDFs open in a page-aware reader with page-by-page navigation. For multi-page material, the Reader and the inspector stay in sync, so the inspector follows the page you are actually viewing.

The Reader has three tabs:

- 
- 
- 

**Page** — the page itself: the scan, image, or PDF page.**Knowledge** — the entities and claims extracted from the current page.**Notes** — your markings and writing, with two sub-modes: **Marks** for annotations on the page and **Notes** for written notes.A toolbar control changes how the reading area and its preview are arranged:

- 
- 
- 

**None** — content only, no preview pane (⌘0).**Standard** — content and preview side by side (⌘1).**Widescreen** — content and preview stacked, with room for the library list, the document canvas, and the reading pane together (⌘2).Editing tools — non-destructive image and page adjustments — live on the Reader canvas toolbar. See Chapter 5.

### The Inspector

The inspector is the panel on the right. It has four sections:

- 
- 
- 
- 

### **Source** — the document itself: extracted text and page content, plus an **Outline** segment for drilling down the document’s structure (chapters, sections, pages).**Notes** — your annotations and free-text research notes for the document, kept separate from the source text.**Knowledge** — the structured material extracted from the document: entities (people, places, organizations, concepts) and claims (who did what, where, and when), with the curation actions described in Chapter 8.**Artifacts** — the outputs that workflows have produced for this document, each with its provenance.Settings

Settings is where you configure Fichero — most importantly, the AI providers and models it can use. You add the providers you want and pick which models each workflow step should use. Because Fichero is model-agnostic, the model picker in a workflow shows only the models you have set up in Settings; if a picker looks empty, open Settings and add a provider first. See Chapter 9 for what stays on your Mac and what leaves it.

### The Canvas and Spatial Views

Beyond the list-like layouts, the library can be arranged spatially. The Canvas layout is a freeform two-dimensional surface where you place documents by hand — useful for laying out a chapter's sources or sorting a folder visually, the way you would spread papers on a desk. The Space layout extends the same idea into three dimensions. Both are early features; positions are saved per folder.
