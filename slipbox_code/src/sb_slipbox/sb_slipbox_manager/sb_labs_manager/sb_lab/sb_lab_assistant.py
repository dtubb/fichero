#src/sb_slipbox_manager/sb_labs_manager/sb_lab/sb_lab_assistant.py

"""
The sb_lab_assistant class is a base agent that defines common behavior for assistants in the LLM lab. It is subclassed by specific implementations like the Extractor, Summarizer, etc.

Assistants are modular agents focused on particular workflow tasks. They are assigned work by the sb_lab_director agent.

Key capabilities:

- Initialize with sb_lab reference 
- Receive prompts and context from director  
- Execute specialized logic for assigned task
- Return output back to director for validation

Typical workflow:

1. Director initializes assistant with sb_lab ref
2. Director assigns task and provides prompt/context
3. Assistant executes its logic and generates output  
4. Assistant returns output to director
5. Director validates output before next step

By inheriting from sb_lab_assistant, agents get prompt processing from sb_lab_agent. They implement task-specific logic in subclassed methods. Assistants enable modular task automation using LLMs.
"""

from src.common import *

from .sb_lab_agent import sb_lab_agent

class sb_lab_assistant(sb_lab_agent):

  def __init__(self, lab, name):
    
    # Explicitly call parent init
    super().__init__(lab, name)  