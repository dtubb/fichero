# src/sb_slipbox_manager/sb_sources_manager/sb_sources_manager.py

from src.common import *
from .sb_source.sb_source import sb_source

import os
import re

import pathlib

class sb_sources_manager():

  def is_valid_folder_name(self, name): 
    """
    Validate folder name matches 'number-text' format.
    Regex explained:
      \d+ - Match 1 or more digits
      -   - Match literal hyphen 
      .+  - Match any text (1 or more characters)
      
     123-source_name - Valid
     source-123 - Invalid
     source - Invalid
    """
    return re.match(r'\d+-.+', name)

  def import_files(self, file_paths):
    """
    Imports list of files into the sources directory
  
    Steps:
    - Validate file paths
    - Call add_source() for each path  
    - add_source() handles creating Source instance
    - Source instance imports the file
    """

    for path in file_paths:
      self.add_source(path)

  def add_source(self, file_path):
    """
    Adds a new source file by:
    1. Creating a Source instance
    2. Appending to sources list 
    3. Calling import method to copy file
  
    Steps:  
    - Create Source, passing self and no load
    - Append Source to sources list
    - Call import method to copy source file

    TODO:
   - Generate proper IDs 
    - Create folder if needed
    - Extract text and metadata
    """

    source = sb_source(self, None, self.directory, False) # Just initializes, with not directory
    
    # Generate ID
    source_id = len(self.sources)+1
    
    self.sources.append(source)

    source.import_original_file(file_path, source_id)
    
  def __init__(self, slipbox_manager):

    self.slipbox_manager = slipbox_manager

    # Get sources dir path
    self.directory = os.path.join(self.slipbox_manager.slipbox.directory, 
                               DEFAULT_SOURCES_FOLDER_NAME)

    log_and_print(f"Initializing Sources Manager",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
                                   
    # Check if sources dir exists, create if needed
    if not os.path.exists(self.directory):
      os.makedirs(self.directory)
        
      log_and_print(f"Creating Sources folder at {self.directory}",
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
                  
    # Get list of source folders
    paths = [f for f in pathlib.Path(self.directory).iterdir()]

    # Sort folders by name (ID) 
    paths.sort(key=lambda f: f.name) 

    self.sources = []

    for path in paths:
    
      if path.is_dir():
        if self.is_valid_folder_name(path.name):
          try:
            source = sb_source(self, path, self.directory, True)
            self.sources.append(source)

          except source_md_file_validation_error as e:
            error_msg = e.args[0]

            log_and_print(f"Skipping sources invalid folder at {path.name} becuase of error: {error_msg}.", LOG_LEVELS.ERROR, VERBOSITY_LEVELS.ERROR)
          
        else:
          log_and_print(f"Sources manager is ignoring folder {path.name} in {self.directory} folder becuase it's folder name is not #-Name", LOG_LEVELS, VERBOSITY_LEVELS.ERROR)
        
      elif not path.is_dir():
        log_and_print(f"Sources manager is ignoring file {path.name} in {self.directory} folder", LOG_LEVELS.ERROR, VERBOSITY_LEVELS.ERROR)

    # Log that it's done.
    
    verbose_print(f"\nLoaded {len(self.sources)} sources", VERBOSITY_LEVELS.INFO)
    log(f"Loaded {len(self.sources)} sources", LOG_LEVELS.INFO)

    log_and_print(f"Done initializing Sources Manager.\n", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
