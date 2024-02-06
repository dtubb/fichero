# src/sb_utils/sb_pdf_to_text.py

import os
from pathlib import Path  

# Import SlipBox’s common functions and constants.
from src.common import *

# Import PDF_Utils for numbering pages
from .sb_pdf_utils import separate_pages

# Import PyPDFLoader for loading PDF files
from langchain_community.document_loaders import PyPDFLoader

# Function to extract text from PDF
def sb_pdf_to_text(input_pdf, output_path):

  # Print verbose statement to confirm extraction
  log_and_print(f"PDF_To_Text: Extract text from: {input_pdf} to {output_path}", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
  
  # Check if input is a PDF file
  if Path(input_pdf).suffix == '.pdf':
    pdf_path = Path(input_pdf) 
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
  loader = PyPDFLoader(str(pdf_path))

  # Use loader to load PDF and split into list of page objects
  # Each page object contains text from that page
  pages = loader.load_and_split()

  # Initialize empty string to hold extracted text
  text = ""

  # Add separator for first page 
  text = separate_pages(1)

  # Extract text from first page
  text += pages[0].page_content


  # Loop over remaining pages  
  for i, page in enumerate(pages[1:]):

    # Add separator    
    text += separate_pages(i+2)

    # Get page content
    text += page.page_content

  # Open output text file for writing 
  try:
    with open(output_file, 'w') as f:
     # Write concatenated text from all pages to output file
      f.write(text)

    # Log that extraction completed successfully 
    log_and_print(f'Text extracted to {output_file}', LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  # Catch any errors and log
  except:
    log_and_print(f'Error writing text file to {output_file}', LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    raise