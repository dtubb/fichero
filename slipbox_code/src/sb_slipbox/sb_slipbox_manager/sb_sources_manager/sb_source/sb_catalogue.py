# src/sb_slipbox_manager/sb_sources_manager/sb_source/sb_catalogue.py

from src.common import *

import os

class sb_catalogue:

  def __init__(self, source, path):
     self.source = source
     self.path = path

     # Build catalogue file path 
     catalogue_file = os.path.join(self.path, f"{self.source.get_source_folder_name()}{DEFAULT_CATALOGUE_FILE_SUFFIX}")

     # Check if catalogue file exists
     if os.path.exists(catalogue_file):
     
       # Load catalogue file 
       # self.catalogue = load_file(catalogue_file)

       log_and_print(f"Catalogue file loaded from {catalogue_file} for {self.source.get_source_folder_name()}", 
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
       
     else:
       # Catalogue file doesn't exist
       self.catalogue = None  

       log_and_print(f"File {catalogue_file} not found for {self.source.get_source_folder_name()}",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  ## Helper function

  def load_file(filepath):
  #  # Function to load file contents
    pass