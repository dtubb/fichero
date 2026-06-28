# What Fichero Is

Fichero is a document library for researchers. It runs primarily as a macOS app
with a local backend engine. It is built for working with primary sources
(scanned archives, PDFs, field notes, historical documents, interview
transcripts), the raw material of research.

You import your sources, read them, extract structured information from them,
annotate them, and write from them. The library and engine are local; AI calls
stay local when you use local providers.

---

## The name

"Fichero" is Spanish for a card-file cabinet. The name recalls the index-card filing systems used by researchers and scholars: Niklas Luhmann's Zettelkasten, the physical card catalogues of archives and libraries, the field notes ethnographers keep, Walter Benjamin's *Arcades Project*. The fichero was the researcher's tool for accumulating and organizing knowledge before computing. Fichero is that idea, rebuilt for archival sources and AI.

---

## Three layers of research work

Fichero organizes research around three phases, each grounded in the source.

### READ: Hermeneutic layer

The READ layer decomposes a source into structured facts: entities, claims, dates, citations, each anchored to the specific page it comes from. This is AI-assisted extraction. Fichero runs workflows (transcription, entity extraction, catalogue generation) across your documents.

The extraction is systematic. Every item carries provenance: which page, which document, which workflow produced it, which model was used. You can review the output, approve it, reject it, or correct it.

This layer answers: *what does this source actually say?*

### THINK: Interpretative layer

The THINK layer is yours. It is your notes and annotations on a reading: what you observed, what you found significant, how this source connects to others in your collection. Fichero gives you annotation tools, a notes system, and an inspector for every document.

This layer answers: *what do I make of this source?*

### WRITE: Synthesis layer *(in development)*

The WRITE layer is where research becomes argument: Zettelkasten-style atomic notes, an outliner, and a writing space connected to your citations and knowledge graph, so you build an argument from your sources and export it with citations intact.

This layer is **planned, not yet built** (the READ and THINK layers exist today; export with citations is partially available). It answers: *what do I want to say about these sources?*

---

## The AI philosophy

Fichero is not built around a chatbot as the main interface. Its center of
gravity is the document library, inspector, search, and workflow surfaces.

The AI in Fichero is there to process source material in inspectable ways. It
extracts entities and claims, transcribes handwriting, and produces structured
artifacts such as catalogues. The important part is that outputs stay tied to
documents, pages, and workflow runs so you can inspect where they came from.

Think of it like a microscope, not a research assistant who tells you what to think. A microscope makes things visible that were hard to see. It does not interpret the slide for you.

The AI does not replace your judgment. It should not be treated as an authority
on what the source means.

You are the analyst. The AI is the instrument.

Fichero can run locally and privately. If you use Apple Foundation Models,
Ollama, LM Studio, or another local provider, your documents stay on your
machine for those calls. If you use a cloud provider, you choose it and control
the API key.

---

## Privacy

Fichero stores library data in a `.fichero` package on your disk. It does not
require an account. If you keep to local providers, your workflow runs stay
local too.

---

## Who it's for

Fichero is written for researchers who work with primary sources: historians, archivists, anthropologists, documentary filmmakers, investigative journalists, anyone processing a collection of scanned or digital documents.

It is useful if you:

- work with archival materials, field notes, interviews, or historical documents
- need to process scanned PDFs, images, or mixed-format collections
- want to extract structured information and build a research record
- care about keeping your data local and under your control

Fichero is a desktop application for macOS. It requires Apple Silicon (M1 or later) and macOS 26 Tahoe or later.
