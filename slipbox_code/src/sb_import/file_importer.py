#src/sb_import/file_importer.py

# Import SlipBox’s common functions and constants.
from src.common import *

from .file_crawler import file_crawler 
from .file_processor import file_processor

# Import glob for wild cards
import glob 
import os

class file_importer:

  @property
  def crawler(self) -> file_crawler:
    # Existing crawler code
    return file_crawler() 

  @property
  def processor(self) -> file_processor:  
    # Existing processor code
    pass
    
  def __init__(self, all_inputs, allowed_extensions, recursive=False):

    self.all_inputs = all_inputs
    self.allowed_extensions = allowed_extensions
    self.recursive = recursive

    # Your original input parsing logic
    wildcard_inputs = []
    for input in self.all_inputs:
      if "*" in input:
        wildcard_inputs.append(input)

    expanded_inputs = []
    for wildcard in wildcard_inputs:
      expanded = glob.glob(wildcard)
      expanded_inputs.extend(expanded)
    
    self.all_inputs = self.all_inputs + expanded_inputs

    # Your original logging
    log(f"Received inputs: {self.all_inputs}", LOG_LEVELS.INFO)
    verbose_print(f"Received inputs: {self.all_inputs}", VERBOSITY_LEVELS.INFO)  

    # Initialize file paths
    self.file_paths = self.all_inputs
    
    # Crawl file paths
    crawled_paths = self.crawler.crawl(self.file_paths, 
                                       self.all_inputs, 
                                       self.allowed_extensions)
    
    # Update File Paths
    self.file_paths = crawled_paths
