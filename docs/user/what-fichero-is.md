# What Fichero Is

Fichero is a document library for researchers. It runs on your Mac. It is built for working with primary sources (scanned archives, PDFs, field notes, historical documents, interview transcripts), the raw material of research.

You import your sources, read them, extract structured information from them, annotate them, and write from them. The whole process stays on your computer.

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

Fichero is not a chatbot. It is not a "sense-making" tool that summarizes your documents and tells you what they mean. That is the researcher's job.

The AI in Fichero does one thing: it surfaces what the sources actually say, in a structured form, with provenance. It extracts entities and claims. It transcribes handwriting. It produces structured catalogues. Every output is traceable back to a page.

Think of it like a microscope, not a research assistant who tells you what to think. A microscope makes things visible that were hard to see. It does not interpret the slide for you.

The AI does not:
- interpret your sources for you
- tell you what the evidence means
- summarize documents in ways that obscure the original
- add anything that isn't in the source
- pretend to be a thinking collaborator

You are the analyst. The AI is the instrument.

Fichero runs as much as possible locally and privately. Where possible, use Apple Intelligence or Ollama so your documents never leave your computer. When you use a cloud provider, you choose it, you control the API key, and Fichero makes no other network calls.

---

## Privacy

Your data stays on your Mac. Fichero stores everything in a `.fichero` library package on your disk. There is no telemetry, no analytics, no cloud sync, and no account required.

The only network traffic is to the AI provider you choose, and only when you run a workflow. If you run everything locally (Apple Intelligence or Ollama), Fichero makes no network calls at all.

---

## Who it's for

Fichero is written for researchers who work with primary sources: historians, archivists, anthropologists, documentary filmmakers, investigative journalists, anyone processing a collection of scanned or digital documents.

It is useful if you:

- work with archival materials, field notes, interviews, or historical documents
- need to process scanned PDFs, images, or mixed-format collections
- want to extract structured information and build a research record
- care about keeping your data local and under your control

Fichero is a desktop application for macOS. It requires Apple Silicon (M1 or later) and macOS 26 Tahoe or later.
