<!-- Verified against importers/ingest.py (2026-07-18). -->

# Importing Documents

## Table of Contents

- [Import Methods](#import-methods)
- [Import Modes](#import-modes)
- [Importing Folders](#importing-folders)
- [Drag and Drop](#drag-and-drop)
- [Supported File Types](#supported-file-types)

## Import Methods

Fichero exposes import in several places:

- the add menu in the window toolbar
- sidebar create/import actions
- drag and drop into the library window

The current add menu offers:

- `Link Files...`
- `Copy Files...`
- `Add Files...`

You can also create a new folder before importing, then import into that folder.

## Import Modes

The app and engine currently distinguish three practical import behaviors:

- `Link`: keep the original file in place and add it to the library.
- `Copy`: import a copy into the library-managed storage.
- `Add Files`: exposed in the UI as a third import command; use it when you want the app to take the file into the library rather than just reference it.

Internally, the import service sends the chosen mode to the fichero-server ingest endpoints. Imported files can also request text extraction and automatic embedding as part of ingest.

## Importing Folders

If you import a folder instead of a single file, Fichero detects that automatically and switches to the folder-ingest path. Folder imports:

- run as asynchronous tasks
- can recurse into subfolders
- preserve hierarchy
- report progress while the import is running

This is why larger imports may continue in the background instead of appearing all at once.

## Drag and Drop

The main content area accepts dropped file URLs. In practice:

- dropping files into the window starts an import
- dropping onto specific sidebar folders can target that folder
- Fichero shows import progress and surfaces readable errors from fichero-server when an import fails

For day-to-day use, drag-and-drop is the fastest way to get a pile of scans or PDFs into the library.

## Supported File Types

Fichero is built around broad ingest support. The engine recognises 50+ file extensions across:

- PDFs and common document formats
- images and scans
- audio and video
- archives and related source material

For the current file-type list, use [supported-file-types.md](./supported-file-types.md).
