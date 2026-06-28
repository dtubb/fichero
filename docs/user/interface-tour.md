# The Interface: A Tour of the Window

This page walks through every major part of the Fichero window so you know what
each control does. It is written for everyday use, so it describes what you see and
click, not what happens behind the scenes. If you are brand new, read
[Getting Started](getting-started.md) first, then come back here when you want to
know what a particular button or pane is for.

*[Screenshot: the full Fichero window, with the sidebar on the left, the library
list in the middle, the reading area, and the inspector on the right.]*

## The window at a glance

A Fichero window has four main regions, left to right:

1. **Sidebar**: the navigator that switches between Library, Search, Chat,
   Workflows, and the other modes.
2. **Library list**: the documents and folders in the current view.
3. **Reading area**: the page, scan, or PDF you are looking at.
4. **Inspector**: the tabbed panel that shows everything Fichero knows about the
   selected document.

You can resize each region by dragging the dividers between them, and you can hide
the sidebar or the inspector when you want more room to read. Each window holds one
library; open a second window to work in another library at the same time.

## The sidebar

The sidebar is the main navigator. It switches the whole window between modes. Each
mode reuses the same window layout, so the list, reading area, and inspector stay
where you expect them.

*[Screenshot: the sidebar showing the mode list.]*

The modes are:

- **Library**: browse your documents and folders. This is the default and where
  you spend most of your time.
- **Search**: run and save searches across the library.
- **Chat**: ask questions about your documents in a conversation.
- **Workflows**: build and run the step-by-step processing pipelines.
- **Chains**: link several workflows into a longer sequence.
- **Activity**: watch workflow runs in progress and review finished ones.
- **Automation**: set up schedules and folder triggers that run workflows for you.
- **Batches**: manage large jobs that process many documents at once.
- **Model Comparison**: run the same prompt against different AI models and compare
  the results side by side.

You can switch sidebar modes with the keyboard using Control plus Command plus a
number key (for example, Control + Command + 1 for Library).

## The library list

In Library mode, the middle pane shows the documents and folders in the current
view. The same set of documents can be shown in four layouts, which you choose from
the toolbar:

- **Icon**: large thumbnails, best for skimming scans and images.
- **List**: a compact vertical list with small previews.
- **Table**: columns of details such as name, type, and dates, with sortable
  headers.
- **Map**: pins for documents that carry a place, useful for fieldwork material.

*[Screenshot: the library list in icon layout and again in table layout.]*

Selection works the way it does in the Finder. Click to select one document, hold
Shift or Command to select several, and use the selection as the input to other
actions, such as running a workflow on everything you picked. Right-click any
document for a menu of actions, and double-click to open it.

## The reading area

When you select a document, the reading area shows it. What appears depends on the
file:

- **Page images and scans** show the image with zoom and a magnifier so you can read
  fine detail.
- **PDFs** open in a page-aware reader with the usual viewer controls and
  page-by-page navigation.
- **Multi-page material** keeps the reading area and the inspector in sync, so the
  inspector follows the page you are actually viewing.

### Reading layouts

A small control in the toolbar changes how the reading area and its preview are
arranged. The three layouts are:

- **None**: content only, no preview pane (keyboard: Command + 0).
- **Standard**: content and preview side by side (Command + 1).
- **Widescreen**: content and preview stacked, with room for the library list, the
  document canvas, and the reading pane together (Command + 2).

*[Screenshot: the reading area in Standard layout next to the same document in
Widescreen layout.]*

## The inspector

The inspector is the tabbed panel on the right. It shows everything Fichero has about
the selected document. The tabs run left to right in the order you usually move
through a source: read the document, see what was marked, see what was noted, then
the structured results, references, edit tools, and finally the file details.

*[Screenshot: the inspector with its row of tabs.]*

The tabs are:

- **Content**: read the document's extracted text and page contents. This is the
  quickest place to read what Fichero pulled out of a scan or PDF.
- **Outline**: drill down the document's structure: chapters, sections, and pages,
  and what is on each.
- **Annotations**: view and edit the highlights and margin notes you have made on
  the document.
- **Notes**: free-text research notes linked to the document. Use this for your own
  thinking, kept separate from the source text.
- **Entities**: the people, places, organizations, and concepts that Fichero
  extracted from the document.
- **Knowledge Graph**: the structured claims (who did what, where, and when) and
  interpretations tied to the document.
- **Citations**: the documents this one cites and the documents that cite it, plus
  the extracted bibliography.
- **Edits**: non-destructive image and page edit operations, so you can adjust a
  scan without altering the original.
- **Info**: the file details: type, size, dates, and where the document is stored.

You will spend most of your time in **Content**, **Annotations**, **Notes**, and
**Entities**. The others are there when you need them.

## Workflows

Workflows mode is where you build the step-by-step pipelines that process your
documents, such as transcribe a scan, then extract people and places, then write a
catalogue entry. You build a workflow visually by placing nodes on a canvas and
connecting them, and you run it on a document or a whole selection.

*[Screenshot: the workflow editor with nodes connected on the canvas.]*

The left pane lists your saved workflows, grouped into folders. The canvas in the
middle is where you arrange and connect the steps. Selecting a node lets you adjust
its settings, such as which AI model it uses. To run a workflow, pick the documents
in Library mode, then choose the workflow from the Run menu or the right-click menu.

For a fuller walkthrough, see
[Curation, Notes & Workflows](curation-notes-workflows.md).

## Chat

Chat mode lets you ask questions about your documents in plain language and get
answers grounded in the sources, with links back to the passages the answer drew
from. It is a way to interrogate your material, and it always shows you where an
answer came from so you can check it.

*[Screenshot: a chat conversation with source links beside the answer.]*

## Search

Search mode runs queries across the whole library and finds documents by meaning, not
only by exact words, so a search for one term can surface related passages. You can
save a search and return to it later from the sidebar.

*[Screenshot: search results with matching passages highlighted.]*

See [Search & Knowledge Graph](search-knowledge-graph.md) for the details.

## Importing documents

You bring material into a library by dragging files and folders onto the window, or
with the Import command. Fichero can either link to files where they already live or
copy them into the library. Folders keep their structure when you import them.

*[Screenshot: dragging a folder of scans into the library.]*

The full options are covered in [Importing Documents](importing-documents.md).

## Settings

Settings is where you configure Fichero, most importantly the AI providers and models
it can use. You add the providers you want (local on-device models, or cloud
providers with your own API key) and pick which models each workflow step should use.

*[Screenshot: the Settings window open to the Models section.]*

Because Fichero is model-agnostic, the model picker in a workflow shows only the
models you have set up here. If a picker looks empty, open Settings and add a provider
first. For what stays on your Mac and what leaves it, see
[AI & Privacy](ai-and-privacy.md).

## Where to go next

- New to the app: [Getting Started](getting-started.md)
- Bringing in material: [Importing Documents](importing-documents.md)
- Reading and marking up sources: [Reading & Editing](reading-and-editing.md)
- Finding things: [Search & Knowledge Graph](search-knowledge-graph.md)
- Processing at scale: [Curation, Notes & Workflows](curation-notes-workflows.md)
- What is private: [AI & Privacy](ai-and-privacy.md)
