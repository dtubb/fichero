# src/sb_slipbox_manager/sb_references_manager/sb_references_manager.py

from src.common import *
import os

class sb_references_manager():

  def __init__(self, slipbox_manager):

    self.slipbox_manager = slipbox_manager

    # Get slips dir path
    self.directory = os.path.join(self.slipbox_manager.slipbox.directory,
                               DEFAULT_REFERENCES_FOLDER_NAME) 

    log_and_print(f"Initializing References Manager at {self.directory}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    # Check if slips dir exists, create if needed
    if not os.path.exists(self.directory):
      os.makedirs(self.directory)
      
      log_and_print(f"Creating References folder at {self.directory}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
                  
    log_and_print(f"Done Initializing References Manager.",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
    # class Slip:
#
#  def __init__(self, filepath):
#    self.filepath = filepath