# Chapter 1. Introducing Fichero


### About Fichero

Fichero is a document library with AI workflows. It is an open-source app for you (researchers, academics, students, writers, journalists) to keep track of primary and secondary sources: scanned archives, PDFs, field notes, historical documents, interview transcripts. You can import your sources, read them, extract structured information from them, annotate them, and work with them. It was developed to make it easy to read long and complex archives, using AI as a tool to assist in transcribing documents and extracting other useful structured data. Using Fichero, you can read source documents and process them with AI workflows, while always being able to see the sources.

The word Fichero is literally from a Spanish for a card-file cabinet. The index-card filing systems researchers and scholars have long used: Walter Benjamin’s *Arcades Project*; Niklas Luhmann’s Zettelkasten; the physical card catalogues of archives and libraries; or indeed the field notes ethnographers and archival notes historians have always kept. Such card catalogues are a tool for accumulating and organizing knowledge.

Fichero is an app for Apple devices, with a server built using open source tools. It is primarily a macOS app, with iPhone and iPad apps that connect to a Mac. It is in development, and it is open source.

### Who is Fichero For?

Fichero is written for researchers who work with primary sources: historians, archivists, anthropologists, investigative journalists. Its audience is anyone processing a collection of scanned or digital documents. It is useful for:

- 
- 
- 

<!-- -->

- 
- 

### **Anthropologists and ethnographers:** Field notes, interview transcripts, recordings, and photographs can live in one library alongside archival materials. You can annotate and keep notes separate from, but linked to, your sources.**Historians and archival researchers:** Historians, anthropologists, and others often collect (tens or hundreds) of thousands of photographed pages of archival documents, in mixed condition, often in hard-to-read handwritten (or paleographic) scripts. Fichero has transcription workflows for difficult historical scripts, which, when run with a powerful enough AI model, can turn page images into searchable text, while each transcription stays anchored to the exact image (and if possible word) it came from, so you can always check the AI against the original.**Archivists and librarians:** Fichero offers workflows to extract structured inventories from scanned collections, and a knowledge graph to connect entities and claims with provenance back to the page. It is also easy to edit and curate extracted data.**Students and researchers:** Researchers collect materials (journal articles and books, recordings, video, spreadsheets). Fichero imports many different file types into a searchable library. After you transcribe and catalogue your sources, you can search using a full-text and semantic vector database and navigate a knowledge graph index.**Anyone who wants to control their research.** Fichero runs on your Mac, with your library on your own disk. While libraries can be shared with your own iOS devices, or other Macs, including other people, Fichero is not a hosted web service.How does Fichero Work?

Fichero has two parts: a native app for Apple devices and a backend server. The backend server handles storage, search, workflows, and knowledge-graph processing; the app is the interface on top. Your library lives in a .fichero package on your own disk.

Fichero organizes research around two layers, each grounded in source materials. Fichero lets you use workflows, running locally or in the cloud, to process them.

#### The READ layer

The READ layer decomposes a source into structured facts: entities, claims, dates, citations — each anchored to the specific page it comes from. This is AI-assisted extraction. Fichero runs workflows (transcription, entity extraction, catalogue generation, and so on) across your documents.

#### The AI philosophy

Fichero's main interface is a sidebar showing your libraries and source materials, a library view, a chat interface, and an inspector. The AI in Fichero is there to process source material in inspectable ways: it transcribes handwriting, extracts entities and claims, and produces structured artifacts such as catalogues. Its output stays tied to documents, pages, and workflow runs so you can always see where a fact came from. Interpretation is yours.

### How to Use This Manual?

Chapters 2–4 get you running: installing Fichero, learning the window, and building a library. Chapters 5–8 cover reading, annotating, running workflows, searching, and curating the knowledge graph. Chapter 9 explains what stays on your Mac and what leaves it. Chapter 10 answers common questions, and the appendices hold reference material.
