# About Fichero

Fichero is a work in progress. At its core, it's an app that lets you use
cutting-edge machine-learning techniques and prompts in a repeatable,
programmatic way on documents.

I've built it to do transcription of handwritten documents using vision language
models, and to produce catalogues — but the approach could be used for other
tasks. The basic idea: rather than having an AI control how things are done, in
ways that are harder to understand, Fichero gives you — the user — a way to
visually build these steps yourself. It also gives you a vector database, a
knowledge graph, an ontological layer, MCP tools, and more in the future.

Under the hood, Fichero is a FastAPI server connecting to a DuckDB database. I've
written it primarily for historians and archivists, but it's ultimately a tool
to experiment with using large language models in a programmatic, methodological,
step-by-step way that helps you with your work.

Fichero is model-agnostic. It works with open-source models as well as
commercial providers — you only need to get yourself an API key. If you want to
run models locally, you can do so with Ollama or LM Studio.

The aim of Fichero is to move beyond the chat, and beyond the agentic model — to
give you more control and insight into how AI does its work: steps you want to be
able to reproduce across multiple documents. This is an app that aims to make the
power of AI accessible, but also searchable and readable. AIs are incredibly
powerful; the aim here is to make them more navigable and transparent —
transparent not only to yourself, but to other people.

What do I mean by that? If things are invisible to the user — hidden in a
database or a vector store — it's hard to know what's going on under the covers.
With Fichero, the aim is to make things visible, and therefore more accessible.

Fichero is a work in progress.
