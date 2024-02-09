# Andy Imports
import asyncio
import typer 
import requests
import srsly
from pathlib import Path
from typing_extensions import Annotated
from rich.progress import track

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

class summary_json(BaseModel):
  description_and_summary: str = Field(description="Description and concise summary of text.")

class qa_critique_json(BaseModel):
    error: str = Field(description="Error")
    correction: str = Field(description="Correction")
    
def main(source_file: str,
         output_file: str = "output.txt",
        llm_model: str = "mistral:instruct"
        ):
  """
  SUMMARIZING source file, and return as a JSON.
 
  If --llm_modell is used you can choose the model to use: mistral, mixtral, gpt 3.5, gpt 4
  """
  # Load source_file
  try:
      with open(source_file, 'r', encoding='utf-8') as file:
          source = file.read()
  except FileNotFoundError:
      print("The file was not found.")
  except Exception as e:
      print(f"An error occurred: {e}")

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
  print("Extracting Summary")  

  output_parser = JsonOutputParser(pydantic_object=summary_json)

  prompt_template = """Describe and summarize in your own words the SOURCE in Spanish. SAY NOTHING ELSE.
    
RETURN AS JSON.

SOURCE:
{source}"""

  if llm_model == "gpt-4" or llm_model == "gpt-3.5-turbo-instruct":

    format_instructions = output_parser.get_format_instructions()
    prompt = PromptTemplate(
      template=""""Describe and summarize in your own words the SOURCE in Spanish. SAY NOTHING ELSE.
    
{format_instructions}

SOURCE:
{source}""",
      input_variables=["source"],
      partial_variables={"format_instructions": output_parser.get_format_instructions()},
    )
  else: #Not Open AI.
      format_instructions = "Return as JSON"
      prompt = ChatPromptTemplate.from_template(f"{prompt_template}")

  chain = prompt | llm | output_parser
  extracted_summary = chain.invoke({"source": f"{source}"})
  pprint.pprint(extracted_summary)

  ## Extract Names
  print("\nRunning QA on Extracted Summary…\n")
  prompt_template = """Compare the SUMMARY to the SOURCE, which is is an archive, and offer a rewrite of the SUMMARY to fix errors. SAY NOTHING ELSE. WORK IN SPANISH.

JSON of SUMMARY:
{extracted_summary}
   
SOURCE:
{source}  
""" 

  prompt = ChatPromptTemplate.from_template(f"{prompt_template}")
  output_parser = JsonOutputParser(pydantic_object=qa_critique_json)
  chain = prompt | llm | output_parser
  qa_recomendations = chain.invoke({"source": f"{source}",
                      "extracted_summary": f"{extracted_summary}"})
                      
  pprint.pprint(qa_recomendations)

  print("\nCleaning up Extracted Summary based on QA…\n")
  prompt_template = """Implement quality assurance recommendations to fix SUMMARY of SOURCE in Spanish. MAKE NO OTHER CHANGES. SAY NOTHING ELSE. 

JSON of QUALITY ASSURANCE RECOMMENDATIONS:
{qa_recomendations}

JSON of SUMMARY:
{extracted_summary}
""" 

  prompt = ChatPromptTemplate.from_template(f"{prompt_template}")
  output_parser = JsonOutputParser(pydantic_object=summary_json)
  chain = prompt | llm | output_parser
  fixed_summary = chain.invoke({"extracted_summary": f"{extracted_summary}",
                      "qa_recomendations": f"{qa_recomendations}"})  
   
  print("\nFixed Summary:")
  pprint.pprint(fixed_summary)

  with open(output_file, 'w') as f:
    json.dump(fixed_summary, f)
  
if __name__ == "__main__":
    typer.run(main)