# Andy Imports
import asyncio
import typer 
import requests
import srsly
from pathlib import Path
from typing_extensions import Annotated
from rich.progress import track
import json
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field

# Old LangGraph imports
from langchain.schema import AgentAction, AgentFinish
from langchain import hub
from langchain.agents import create_openai_functions_agent

from langchain_openai.chat_models import ChatOpenAI
from langchain_core.agents import AgentFinish
from langgraph.graph import END, Graph
from langchain.globals import set_debug
from langchain.globals import set_verbose
from langchain.agents import Tool
from langchain.agents import AgentType, initialize_agent, load_tools
from langchain.tools import StructuredTool  
from langchain.prompts import PromptTemplate
from langchain.chains.llm import LLMChain
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import AgentAction, AgentFinish

from langchain import hub
from langchain.agents import create_openai_functions_agent
from langchain_openai.chat_models import ChatOpenAI

from langchain_core.runnables import RunnablePassthrough
from langchain_core.agents import AgentFinish

from langgraph.graph import END, Graph

from langchain.globals import set_debug
from langchain.globals import set_verbose

from langchain.agents import AgentType, initialize_agent, load_tools

import inspect
import pprint

# New LangGraph imports
import json
import operator
from typing import Annotated, Sequence, TypedDict
from langchain import hub
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain_community.chat_models import ChatOllama
from langchain_community.vectorstores import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.runnables import RunnablePassthrough
from langchain_mistralai.chat_models import ChatMistralAI
from langchain_openai import ChatOpenAI
from typing import Dict, Any

class summary_json(BaseModel):
  description_and_summary: str = Field(description="Prompt applied to text.")

class qa_critique_json(BaseModel):
    error: str = Field(description="Error")
    correction: str = Field(description="Correction")

class Variables(BaseModel):
    variables: Dict[str, Any]

def main(source_file: str="source.txt",
         prompt_template_file: str="prompt.txt",
         variables_file: str="variables.txt",
         output_file: str ="output.txt",
         llm_model: str = "mistral:instruct"
         ):
  """
  Load a source_file as a source, then load a prompt file with variables, 
  and then load the variables from a file, apply this and save it as 
  the source file name + the file name of the prompt.
 
  If --llm_modell is used you can choose the model to use: mistral, mixtral, gpt 3.5, gpt 4
  """
  
  # Load source_file contents
  try:
      with open(source_file, 'r', encoding='utf-8') as file:
          source = file.read()
  except FileNotFoundError:
      print(f"The source file {source_file} was not found.")
      return
  except Exception as e:
      print(f"An error occurred while reading {source_file}: {e}")
      return

  # Load prompt_template_file contents
  try:
      with open(prompt_template_file, 'r', encoding='utf-8') as file:
          prompt_template = file.read()
  except FileNotFoundError:
      print(f"The prompt file {prompt_template_file} was not found.")
      return
  except Exception as e:
      print(f"An error occurred while reading {prompt_template_file}: {e}")
      return

  # Load variables from variables_file
  try:
      with open(variables_file, 'r', encoding='utf-8') as file:
          variables = json.load(file)
          
  except FileNotFoundError:
      print(f"The variables file {variables_file} was not found.")
      return
  except Exception as e:
      print(f"An error occurred while reading {variables_file}: {e}")
      return

  # Setup LLM
  if llm_model == "mistral:instruct":
    llm = ChatOllama(model="mistral:instruct", format="json", temperature=0)
    print("Using 'mistral:instruct'.")

  elif llm_model == "mistral:7b-instruct":
    llm = ChatOllama(model="mistral:7b-instruct", format="json", temperature=0)
    print("Using 'mistral:7b-instruct'.")

  elif llm_model == "mixtral:8x7b":
    llm = ChatOllama(model="mixtral:8x7b", format="json", temperature=0)
    print("Using 'mixtral:8x7b'.")

  elif llm_model == "mixtral:instruct":
    llm = ChatOllama(model="mixtral:instruct", format="json", temperature=0)
    print("Using 'mixtral:instruct'.")

  elif llm_model == "gpt-4":
    llm = ChatOpenAI(model=f"gpt-4", temperature=0)
    print("Using 'gpt-4'.")

  elif llm_model == "gpt-3.5-turbo-instruct":
    llm = ChatOpenAI(model=f"gpt-3.5-turbo-instruct", temperature=0)
    print("Using 'gpt-3.5-turbo-instruct'.")

  else:
    llm = ChatOllama(model="mistral:instruct", format="json", temperature=0)
    print("Model not found, using 'mistral:instruct'.")

  ## Extract Names
  output_parser = JsonOutputParser(pydantic_object=summary_json)

  # Apply the prompt template with variables
  prompt = PromptTemplate(
      template=prompt_template,
      input_variables=["source"]
  )


  if llm_model == "gpt-4" or llm_model == "gpt-3.5-turbo-instruct":

    format_instructions = output_parser.get_format_instructions()
    prompt = PromptTemplate(
      template="""Use the Zettelkasten method to tag this source with 3 tags, based on the tags provided. If no tags fit, create 3 tags.
  
RETURN AS JSON.

SLIP:
{source}

TAGS:
{tags}""",
      input_variables=["source"],
      partial_variables={"format_instructions": output_parser.get_format_instructions()},
    )
  else: #Not Open AI.
      format_instructions = "Return as JSON"
      prompt = ChatPromptTemplate.from_template(f"{prompt_template}")

  # Merge 'source' and all items from 'variables' into one dictionary
  invoke_arguments = {"source": source}
  invoke_arguments.update(variables)

  chain = prompt | llm | output_parser
  result = chain.invoke(invoke_arguments)

  pprint.pprint(result)

  # Determine the output filename
  if not output_file:
      source_file_name = Path(source_file).stem
      prompt_template_file_name = Path(prompt_template_file).stem
      output_file = f"{source_file_name}_{prompt_template_file_name}.txt"

  # Save the result
  with open(output_file, 'w', encoding='utf-8') as f:
      json.dump(result, f, ensure_ascii=False, indent=4)

  pprint.pprint(f"Output saved to {output_file}")

if __name__ == "__main__":
    typer.run(main)