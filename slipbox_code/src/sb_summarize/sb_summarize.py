#src/summarize/sb_summarize.py



import os
import time 
from pathlib import Path  

# Import langchain's common functions and constants.
from langchain_community.document_loaders import PyPDFLoader
from langchain.chains.llm import LLMChain
from langchain.prompts import PromptTemplate
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain_openai.chat_models import ChatOpenAI
from langchain.chains import RefineDocumentsChain
from langchain.prompts import PromptTemplate

# Import SlipBox’s common functions and constants.
from src.common import *

# If you want to try GPT4All, use this.
# from langchain.llms import GPT4All

# Load pages
def load_pdf_pages(pdf_path):
  # Create a PDF loader for the given file
  # Task for Todo List: This can be refactored to the PDF utilities
  loader = PyPDFLoader(pdf_path)
  
  # Load the PDF and split it into an array of documents
  # Each document in the array represents one page of the PDF
  pages = loader.load_and_split()

  return pages
  
def sb_summarize(pdf_path, output_path, size):

  # Check if input is a PDF file
  if Path(pdf_path).suffix == '.pdf':
    pdf_path = Path(pdf_path) 
  else:
    raise ValueError("Invalid PDF input")

  # Check if output is a directory
  if os.path.isdir(output_path):
    
    # If directory, use PDF filename as output file
    filename = pdf_path.stem + '.txt'
    output_file = os.path.join(output_path, filename)

  else:
    # If not a directory, treat as file path 
    output_file = output_path

  # Create PyPDFLoader object for the input PDF
  # This will handle loading the PDF
  pages = load_pdf_pages(str(pdf_path))
  
  
  # Define a template for the summarization prompt
  # The "{pages}" placeholder will be replaced with the actual text to be summarized 
  prompt_start = f"""
  Write a concise {size} word summary of the following:
  """

  # ... load pages ...

  prompt_end = f"""

  CONCISE {size} WORD SUMMARY: 
  """

  prompt_template = prompt_start + "{pages}" + prompt_end
  
  verbose_print(f"Using prompt: {prompt_template}", VERBOSITY_LEVELS.INFO)

  # Create a PromptTemplate object from the template string
  # This object will be used to generate prompts for the language model
  prompt = PromptTemplate.from_template(prompt_template)

  # Initialize the language model
  # The temperature parameter determines the randomness of the model's output
  # A lower value results in more deterministic output
  # The model_name parameter specifies the name of the model to use
  llm = ChatOpenAI(temperature=0, model_name="gpt-4-1106-preview")

  # Create a LLMChain object
  # It encapsulates the process of generating a summary by the language model
  llm_chain = LLMChain(llm=llm, prompt=prompt)

  # Create a StuffDocumentsChain object
  # It uses the LLMChain to generate summaries for an array of documents
  stuff_chain = StuffDocumentsChain(
    llm_chain=llm_chain, document_variable_name="pages"
  )

  # Run the StuffDocumentsChain on the array of documents (pages)
  # This generates a summary for each document and returns an array of   
  
  verbose_print(f'Sending to ChatGPT', VERBOSITY_LEVELS.INFO)

  summaries = str(stuff_chain.run(pages)) 

  verbose_print(f'Trying to write file', VERBOSITY_LEVELS.INFO)
  
  # Write summaries 
  with open(output_file, 'w') as f:

    for summary in summaries:
      f.write(summary)

  time.sleep(10)
  
# Usage:
# sb_summarize('paper.pdf', 'summary.txt', length=100)