# Fichero Weasel. Run LLM prompts on files. Written in Python.

Import  OCR Extract Catalogue  Reference  Write Tag  Link

**Documentation:** https://fichero.hewlab.ca

**Source Code:** https://github.com/dtubb/fichero

Extraction and organization of note cards from source material powered by LLM.

Fichero—from the Spanish for "box of index cards"—is a CLI applications to help build a *fichero*, an interconnected box of index cards about source material. It helps researchers in the social sciences and humanities unlock an Swiss-Army Knife of easy to edit LLM prompts, to build, read, edit a dynamic, accessible *fichero* from the terminal.

The key features are:

- Allows users to easily and iteratively build a box of *fiches* based on sources. 
- Produces folder hierarchy with text-files that are  of easy to read, understand, *rewrite*, and reuse.
- Files are easy to integrate into a knowledge management app (Obsidian, Tinderbox, DevonThink, etc), or a Jekyl and Pandoc powered static website. 
- Builds a *fichero*, an interconnected box of *fiches* index cards about source material.
- Written for researchers in the social sciences and humanities, who have long made collections of short notes on a research topic.
- Builds on the methods of a historians archival-notes, an anthropologists field-notes.
- Inspired the Walter Benjamin's [Arcades Project](https://en.wikipedia.org/wiki/Arcades_Project), Niklas Luhmann's [Zettelkasten method](https://en.wikipedia.org/wiki/Zettelkasten), and Sönke Ahrens [slip-box](https://www.soenkeahrens.de/en/takesmartnotes) method. 
- Simplifies automatically producing *fiches* about source material (notes, articles, books, and images) in jpg, pdf,  txt, md, word, and other formats.). 

- Creates *fiches* with metadata, catalogue entries, summaries, notes on atomic ideas, references, tags, links, and quotes from a variety of sources, powered by easy to edit LLM prompts, connected to many LLM models. 

Key technical features:

- Written in Python.
- Uses Google Vision, for text extraction.
- Hooks into [eScriptorium-Vision](https://github.com/upenndigitalscholarship/escriptorium-vision) to fetch the images from eScriptorium, run HTR on the images, upload the transcriptions back to eScriptorium, and then extract the text.
- Powered by [LangChain](https://www.langchain.com) Large Language Models
  - Connects to the cloud (e.g. OpenAi's ChatGPT 3.5 and 4).
  - Run LLMS locally with [Ollama](https://ollama.ai) or [GPT4All](https://gpt4all.io), and use [HuggingFace](https://huggingface.co) models— e.g. [Mistral:Instruct](https://mistral.ai/news/announcing-mistral-7b/) or [Mixtral 8x7B](https://mistral.ai/news/mixtral-of-experts/)
- Writes Markdown, with metadata in human-readable [YAML]() format, using [python-frontmatter](https://github.com/eyeseast/python-frontmatter)
- Easy to use command-line interface (CLI), made with [Typer](https://typer.tiangolo.com).
- Prettified terminal output, with [Rich](https://rich.readthedocs.io/en/stable/index.html).
