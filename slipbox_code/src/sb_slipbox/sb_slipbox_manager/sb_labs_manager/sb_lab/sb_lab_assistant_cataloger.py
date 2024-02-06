# src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_assistant_cataloger.py

#src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_assistant_cataloger.py

# The sb_lab_assistant_cataloger is an agent (powered by LangGraph) focused on cataloging ocr_cleaned-up text extracts from source documents. It is initialized by the sb_lab agent, with the cleaned text. The cataloger's key task is to extract meta data text for further processing and reference, ensuring easy retrieval and maintaining a structured record of all documents handled.

Key responsibilities:

- Receive cleaned text and source file from director
- Catalog text extracts with appropriate metadata
- Maintain a structured and searchable text database
- Provide easy retrieval mechanisms for the cleaned text
- Ensure all text extracts are properly versioned and stored
- Return confirmation of cataloging to director

This allows for efficient storage and retrieval of documents within the slipbox system, making it easier for other agents to access and reference the documents as needed.

from src.common import *
from .sb_lab_assistant import sb_lab_assistant

from langchain.agents import Tool
from langchain.agents import AgentType, initialize_agent, load_tools

from langchain.tools import StructuredTool

class sb_lab_assistant_cataloger(sb_lab_assistant):

  # Define the tool function
  def catalog(goal, source):
    log_
    return """"""
  
  def __init__(self, lab, name):
    
    # Explicitly call parent init  
    super().__init__(lab, name)   
      
    # Initialize tool   
    print("\tDefining LAB > catalogue_tool")
    self.tool = StructuredTool.from_function(
      name="Assistant_Cataloger",
      func=self.catalog,  
      description="Extracts entities from text into structured catalog",
      handle_tool_error=True,
      verbose=True
    )