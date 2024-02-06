# src/sb_slipbox_manager/sb_slips_manager/sb_slips_manager.py

from src.common import *
import os

class sb_slips_manager():

  def __init__(self, slipbox_manager):
    self.slipbox_manager = slipbox_manager  

    # Get slips dir path
    self.directory = os.path.join(self.slipbox_manager.slipbox.directory,
                               DEFAULT_SLIPS_FOLDER_NAME) 

    log_and_print(f"Initializing Slips Manager at {self.directory}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    # Check if slips dir exists, create if needed
    if not os.path.exists(self.directory):
      os.makedirs(self.directory)
        
      log_and_print(f"Creating Slips folder at {self.directory}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)


    log_and_print(f"Done Initializing Slips Manager.",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

# class Slip:
#
#  def __init__(self, filepath):
#    self.filepath = filepath