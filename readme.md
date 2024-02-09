# Fichero: Build a Extract Text and Build Digital Card Catalogue from Archives
Read Catalogue Export
**Source Code:** https://github.com/dtubb/fichero

Fichero is an set of workflows using open-source tools to extract text, generate metadata, and build a digital card catalogue or *fichero* from archival documents.

It uses machine learning pipelines with digital images.

- Natural language processing with spaCy to detect named entities and keywords.
- Summarization, timeline generation, and metadata extraction by querying large language models through LangChain/HuggingFace.
- Exporting the extracted information as Markdown files organized into a digital *fichero* or slip-box system.
- Mapping metadata visually with Nomic's Atlas. 
- Builds a static website to browse the catalogue using Jekyll.

Fichero simplifies creating a searchable, interconnected digital card catalogue. The Markdown output integrates with knowledge management tools like Obsidian.

## Fichero
Fichero is designed for archivists, librarians, researchers in the humanities and social sciences. It builds on traditional practices like a historian's archival notes or an anthropologist's field notes.

The focus is on open source tools for extracting semantic information from documents to build a digital catalogue. 

Fichero—from the Spanish for "box of index cards"—is a set of Weasel workflows to build a *fichero*, an interconnected box of index cards about source material. It helps researchers in the social sciences and humanities unlock an Swiss-Army Knife of machine learning tools to read text, build an catalogue, and export a dynamic, accessible *fichero* from the terminal.

- Allows for the building of an box of *fiches* based on sources. 
- Produces folder hierarchy with text-files easy to read, explore, *rewrite*, and reuse.
- Builds a *fichero*, an interconnected box of *fiches* index cards about source material.
- Files are can be opened in a knowledge management app (Obsidian, Tinderbox, DevonThink, etc), or converted to  static website with Jecyyll. 
- Written for researchers in the social sciences and humanities, who have long made collections of short notes on a research topic.
- Builds on the methods of a historians archival-notes, an anthropologists field-notes, and is inspired the Walter Benjamin's [Arcades Project](https://en.wikipedia.org/wiki/Arcades_Project), Niklas Luhmann's [Zettelkasten method](https://en.wikipedia.org/wiki/Zettelkasten), and Sönke Ahrens [slip-box](https://www.soenkeahrens.de/en/takesmartnotes) method. 
- Uses machine learning to extract metadata, catalogue entries, summaries, etc.

# Key technical features:
- Weasel workflows
- NLP with spaCy
- Written in Python.
- Hooks into
  - Google Vision, for text extraction.
  - [eScriptorium-Vision](https://github.com/upenndigitalscholarship/escriptorium-vision) to fetch the images from eScriptorium, run HTR on the images, upload the transcriptions back to eScriptorium, and then extract the text.
  - [LangChain](https://www.langchain.com) Large Language Models
    - Connects to the cloud (e.g. OpenAi's ChatGPT 3.5 and 4).
    - Run LLMS locally with [Ollama](https://ollama.ai) or [GPT4All](https://gpt4all.io), and [HuggingFace](https://huggingface.co) models— e.g. [Mistral:Instruct](https://mistral.ai/news/announcing-mistral-7b/) or [Mixtral 8x7B](https://mistral.ai/news/mixtral-of-experts/)
- Writes Markdown, with metadata in human-readable [YAML]() format.
- Easy to use command-line interface (CLI), made with [Typer](https://typer.tiangolo.com).
- Prettified terminal output, with [Rich](https://rich.readthedocs.io/en/stable/index.html).
