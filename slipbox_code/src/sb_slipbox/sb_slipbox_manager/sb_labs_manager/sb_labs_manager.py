# src/sb_slipbox_manager/sb_labs_manager/sb_labs_manager.py

"""
sb_labs_manager.py

This module defines the sb_labs_manager class which is responsible for managing "LLM Labs" associated with a slipbox instance. 

The sb_labs_manager initializes with a reference to the parent slipbox. It can create new sb_lab instances and track them in a labs list.

Key capabilities:

- Initialize with slipbox reference
- Create new labs (sb_lab instances)
- Maintain lab list
- List existing labs

The labs manager provides a simple interface to give labs tasks to deal with sources, extracts, tags, slips, and so forth, that leverages AI under the hood.
"""

from src.common import *
from .sb_lab.sb_lab import sb_lab
from src.sb_utils.sb_langchain_json_to_dictionary import sb_langchain_json_to_dictionary

class sb_labs_manager():

  def do_task(self, task, source):

    lab = self.create_lab()
    
    log_and_print(f"""Tasking {lab.get_name()} with task:
    
TASK: {task}
    
SOURCE: 
=================
{source}
=================
""", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    _result = lab.do_task(task, source)
    
    self.destroy_lab(lab)

    # Cleanup the result, which is a JSON Object.

    data = sb_langchain_json_to_dictionary(_result)

    return data

  def create_lab(self, name=None):

    if not name:
      name = f"Lab {self.next_lab_num}"

    lab = sb_lab(self.slipbox_manager, name)

    self.next_lab_num += 1
    self.active_labs.append(lab)

    return lab

  def destroy_lab(self, lab):

    log_and_print(f"Shutting down the lab {lab.get_name()}.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    self.active_labs.remove(lab)
    lab = None
    
  def __init__(self, slipbox_manager):
    log_and_print(f"Initilaizing the Labs Manager", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    self.slipbox_manager = slipbox_manager
    
    self.active_labs = []
    self.next_lab_num = 1
    self.active_labs[0] = self.create_lab(f"Lab {self.next_lab_num}")

    log_and_print(f"\nDone Initilaizing the Labs Manager",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)