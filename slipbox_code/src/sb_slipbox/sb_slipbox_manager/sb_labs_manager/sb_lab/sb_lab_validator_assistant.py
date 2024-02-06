#src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_validator_assistant.py

"""
The sb_validator is a specialized LLM agent focused on peer review and validation of assistant output.  

It is initialized as a peer to the sb_lab_director and can be assigned validation tasks.

The validator's key responsibilities are:

- Review outputs from assistants like extracts, summaries, etc.  
- Offer constructive critiques and suggestions for improvement
- Check for accuracy - ensure no fabricated content vs source   
- Validate logic, coherence, citation correctness
- Identify any errors, inconsistencies, contradictions
- Recommend re-work by same or other assistants if needed
- Approve output through peer review process

This allows leveraging LLMs for peer review and quality control. The validator acts as an unbiased peer reviewer to validate assistant work. This is key for scholarly integrity and preventing "making up" content.

The validator works collaboratively with the director but can make independent assessments of output quality before advancing workflow. Its specialized focus complements the director's broader oversight.

Together the director and validator ensure robust LLM workflows to build up the slipbox knowledge graph.
"""

from src.common import *

from .sb_lab_agent import sb_lab_agent

class sb_lab_validator_assistant(sb_lab_agent):

  def __init__(self, lab, name):
      
    # Explicitly call parent init
    super().__init__(lab, name)  
    
    # No params required, handled by metaclass
    log_and_print(f"{self.get_name()} in {self.lab.get_name()} initialized. ",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)