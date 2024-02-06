# src/sb_slipbox_manager/sb_extracted_metadata_manager/sb_extracted_metadata_manager.py

from src.common import *
import os

class sb_extracted_metadata_manager():

  def __init__(self, slipbox_manager):
  
    self.slipbox_manager = slipbox_manager

    # Get slips dir path
    self.directory = os.path.join(self.slipbox_manager.slipbox.directory,
                               DEFAULT_EXTRACTED_METADATA_FOLDER_NAME) 

    # Check if slips dir exists, create if needed
    if not os.path.exists(self.directory):
      os.makedirs(self.directory)
        
      log_and_print(f"Creating Extracted Metadata folder at {self.directory}", 
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    log_and_print(f"Initializing Extracted Metadata Manager at {self.directory}", 
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)


    log_and_print(f"Done Initializing the Extracted Metadata Manager", 
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
                      
# class Slip:
#
#  def __init__(self, filepath):
#    self.filepath = filepath