# src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_assistant_summarizer.py

"""
The sb_lab_assistant_summarizer agent generates summaries from source documents. 

It is initialized by the sb_lab_director with the full source text.

The assistant's key task is text summarization - condensing documents into concise overviews.

Key responsibilities:

- Receive full source text from director
- Analyze text to identify key points
- Summarize into a shortened synopsis  
- Return summary to director

This allows capturing the essence of lengthy sources in a condensed format. By summarizing documents, the assistant enables more efficient review of content.

It focuses narrowly on high quality summarization to complement other assistants. Together they build up the networked slipbox from sources.
"""

from src.common import *
from .sb_lab_assistant import sb_lab_assistant

from langchain.agents import Tool
from langchain.agents import AgentType, initialize_agent, load_tools


class sb_lab_assistant_summarizer(sb_lab_assistant):

  # Define the tool function
  def summarize(goal, source):

    # Summarization logic 
      
    return """Este documento parece ser un pagaré y acuerdo de hipoteca entre Manuel María Lozano y el Dr. G.A.P. de la Torre.

En agosto de 1929, Lozano acordó pagar 107 pesos a de la Torre por mercancías recibidas, dentro de 3 meses. Si no pagaba a tiempo, acordó pagar un interés mensual del 2% y hipotecar una casa de su propiedad a de la Torre. El documento fue firmado por Lozano en Condoto, Colombia, con Luis Enrique Bernat y otro testigo como testigos."""

  def __init__(self, lab, name):
    
    # Explicitly call parent init  
    super().__init__(lab, name)   
      
    # Initialize tool   
    self.tool = Tool(
      name="Assistant_Summarizer",
      func=self.summarize,  
      description="Generates summary from full source text",  
      verbose=True
    )