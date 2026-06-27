# Getting Started

## Table of Contents

- [Create or Open a Library](#create-or-open-a-library)
- [Understand the Main Window](#understand-the-main-window)
- [Move Around the Library](#move-around-the-library)
- [What Happens Before The App Is Ready](#what-happens-before-the-app-is-ready)

## Create or Open a Library

When no library is open, Fichero shows a welcome screen with two actions:

- `New Library`
- `Open Library`

Libraries are `.fichero` packages. Opening a library uses a package picker. Creating a new one uses a save panel and automatically adds the `.fichero` suffix if you do not type it yourself.

Fichero can also keep working with temporary unsaved libraries, but the normal user path is to create or open a named `.fichero` package.

## Understand the Main Window

Once a library is open, the app switches to its main workspace.

### Sidebar

The left sidebar is where you change context. Depending on the active mode, it can show:

- the library tree
- saved searches
- chats
- workflows
- activity runs

The mode switcher at the bottom changes what the sidebar and center panel are showing.

### Content Browser

The browser pane shows the current folder or result set. In library mode, the same document set can be shown as:

- icon view
- list view
- table view
- map view

Selection is Finder-like. You can single-select, multi-select, and use the selection as input to other actions such as workflow runs.

### Reading Area

The reading area is where you actually inspect the selected item. Depending on the file type, this may show:

- an image or scanned page
- a PDF page view
- extracted page content
- a knowledge-graph web pane or related reading surface

### Inspector

The inspector is the right-hand panel. Its available tabs depend on the selected document, but typically include:

- Content
- Annotations
- Notes
- Knowledge Graph
- Outline
- Entities
- Artifacts
- Info

Images, PDFs, and page documents also expose an `Edits` tab.

## Move Around the Library

A few behaviors matter early:

- Changing the sidebar selection changes the document set in the browser.
- Changing the browser selection updates the reading area and inspector.
- The app remembers window state such as visible panes, display mode, and some sort settings.
- Search can start from the toolbar even while you are in library mode; when you submit it, Fichero switches into the search surface.

## What Happens Before The App Is Ready

The Fichero app depends on the local fichero-engine server. If fichero-engine is still starting, Fichero shows `Connecting to backend...`. If it cannot connect, the window switches to a connection error state with `Retry` and `Quit`.

That is normal, not a separate offline mode: the Fichero app is a native interface over the local fichero-engine server.
