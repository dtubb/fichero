(AI generated. Not reviewed.)

# Reading, Transcription, and Editing

## Table of Contents

- [Reading Surfaces](#reading-surfaces)
- [Transcription and Extracted Content](#transcription-and-extracted-content)
- [Inspector Tabs You Will Use Most](#inspector-tabs-you-will-use-most)
- [Annotations](#annotations)
- [Notes](#notes)
- [Edits](#edits)

## Reading Surfaces

Fichero uses a single reading workspace that adapts to the selected document.

For page images and scans, you will usually work with:

- the page image itself
- zoom and magnifier tools
- extracted text or page content in related panes

For PDFs, the app uses a PDF reading stack with page-aware navigation and viewer controls. For folders and multi-page material, the inspector and reading panes stay linked to the current page-level context.

## Transcription and Extracted Content

The `Content` tab in the inspector is the quickest place to read what Fichero extracted from a document. In current builds:

- the content tab shows document content rather than generic file metadata
- extracted text and generated outputs are shown through the Content inspector surfaces
- the app keeps the page-focused context in sync so the inspector can follow the page you are actually viewing

For users, the main rule is simple: if the scan and its text both exist, the reading area shows the image or PDF while the inspector helps you inspect the extracted content.

## Inspector Tabs You Will Use Most

### Content

Use `Content` to read extracted document text and page content.

### Outline

Use `Outline` when a source outline is available and you want structured navigation rather than plain reading. It drills down chapters, sections, and pages, and what is on each.

### Entities

Use `Entities` to see the people, places, organizations, and concepts that Fichero extracted from the document.

### Knowledge Graph

Use `Knowledge Graph` for the structured claims (who did what, where, and when) and interpretations tied to the document.

### Citations

Use `Citations` to see the documents this one cites, the documents that cite it, and the document's extracted bibliography.

### Info

Use `Info` for file metadata, dates, path-related details, and related document properties.

The full row of inspector tabs is described in [The Interface: A Tour of the Window](interface-tour.md#the-inspector).

## Annotations

The `Annotations` tab is backed by fichero-server and supports real work, not just display.

You can:

- add a quick note annotation from the add bar
- search existing annotations by text, tags, or claim id
- click an annotation row to reveal its source page or region
- edit annotation text
- copy cropped content from region- or span-based annotations
- promote an annotation into a claim
- delete an annotation

If there are no annotations yet, the empty state points you toward adding a note or highlighting a region on the page.

## Notes

The `Notes` tab is separate from annotations. It is for free-text notes linked to the current document.

You can:

- add a new note inline
- edit note text in place
- delete notes
- review saved notes with their current metadata

Use notes for document-level commentary. Use annotations when the note should stay tied to a page region, text span, or claim.

## Edits

Images, PDFs, and page documents expose an `Edits` tab. If the selected item is not an image, PDF, or page, Fichero tells you that edits are not available for that item type.

The editing surfaces are part of the main document canvas rather than a completely separate subsystem, so reading and editing stay in one workflow.
