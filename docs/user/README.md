(AI generated. Not reviewed.)

# Fichero User Manual

New to Fichero? Start with [What Fichero Is](./what-fichero-is.md).

This manual describes the Fichero app as it exists in the current SwiftUI client and Python engine. It focuses on the real library, reading, search, knowledge-graph, notes, annotation, and workflow behavior implemented under `fichero/fichero/`.

## Table of Contents

- [What Fichero Is](./what-fichero-is.md)
- [Installing Fichero](./install.md)
- [AI and Privacy](./ai-and-privacy.md)
- [Tailscale Private Transport](../remote-backend-tailscale.md)
- [Getting Started](./getting-started.md)
- [The Interface: A Tour of the Window](./interface-tour.md)
- [Importing Documents](./importing-documents.md)
- [Reading, Transcription, and Editing](./reading-and-editing.md)
- [Search, Entities, and the Knowledge Graph](./search-knowledge-graph.md)
- [Curation, Notes, Annotations, and Workflows](./curation-notes-workflows.md)

## What Fichero Is

Fichero is a macOS document library. Each window works with one `.fichero` library package. Inside that library you can:

- import files and folders
- browse them in icon, list, table, and map layouts
- read page images, PDFs, extracted text, and generated artifacts
- inspect entities, claims, annotations, and notes
- run workflows such as transcription and catalogue-style extraction

## How The Window Is Organized

In library mode, the main window is a four-part workspace:

1. Sidebar on the left for libraries, folders, saved searches, workflows, and activity.
2. Content browser in the center for the current folder or search results.
3. Reading area for the selected document or page.
4. Inspector on the right with tabs for content, outline, annotations, notes, entities, knowledge graph, citations, edits, and file info. See [The Interface: A Tour of the Window](./interface-tour.md) for what each one does.

The exact panes you see depend on what is selected, but that overall structure stays the same.

## Related Reference Pages

- Supported formats: [../supported_file_types.md](../supported_file_types.md)
- Current UI map used by the team: [../UI_MAP.md](../UI_MAP.md)
