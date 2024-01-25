# Fichero. Run LLM prompts on files. Written in Python.

Rum Prompts Extract Metadata  Catalogue  

**Documentation:** https://fichero.hewlab.ca

**Source Code:** https://github.com/dtubb/fichero

Key features:

- Run a prompt on a file.
- Written in Python.
- Easy to use command-line interface (CLI), made with [Typer](https://typer.tiangolo.com).
- Prettified terminal output, with [Rich](https://rich.readthedocs.io/en/stable/index.html).
- Powered by [LangChain](https://www.langchain.com) Large Language Models
  - Connects to the cloud (e.g. OpenAi's ChatGPT 3.5 and 4).
  - Run LLMS locally with [Ollama](https://ollama.ai) or [GPT4All](https://gpt4all.io), and use [HuggingFace](https://huggingface.co) models— e.g. [Mistral:Instruct](https://mistral.ai/news/announcing-mistral-7b/) or [Mixtral 8x7B](https://mistral.ai/news/mixtral-of-experts/)

# Input

- source
- prompt
- output
- config
  - llm and model
  - open_ai (gpt 3.5, 4, etc)
  - ollama (recomended mistral:isntruct or mixtral7x8b:isntruct)
  - gpt4all (recomended mistral:isntruct or mixtral7x8b:isntruct)
  - ollama (recomended mistral:isntruct or mixtral7x8b:isntruct)

  - temperature
  - max toxens
  - other parematers
  - verbose
  - debug