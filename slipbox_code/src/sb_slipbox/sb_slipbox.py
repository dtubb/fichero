# src/sb_slipbox.py

# Import SlipBox’s common functions and constants.
from src.common import *

import os

from .sb_slipbox_manager.sb_slipbox_manager import sb_slipbox_manager 

# from sb_managers import source_manager, extract_manager, slip_manager, reference_manager, tag_manager
# from sb_generators import extractor, reference_generator, slip_generator, tag_generator, link_generator  
# from sb_summarizers import summary_generator
# from sb_clients import langchain_client, chatgpt_client

class sb_slipbox:

  def import_files(self, file_paths):
  
    """
      Imports the list of file paths into the SlipBox system
      Passes files to manager to handle actual import
      
      Steps:
      - Log about starting file import
      - Call manager's import_files() 
      - Manager will:
        - Create Source objects
        - Copy or sym linl files to source folder
        - Extract text and metadata
        - Generate IDs
        - Load Source objects
    """
    log_and_print("Importing files into SlipBox", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    self.manager.import_files(file_paths)   

    # self.source_dir = config['source_dir'] 
    # self.output_dir = config['output_dir']

    # self.source_manager = source_manager(self.source_dir)
    # self.extract_manager = extract_manager(self.output_dir + '/extracted')
    # self.slip_manager = slip_manager(self.output_dir + '/slips')
    # self.reference_manager = reference_manager(self.output_dir + '/refs')
    # self.tag_manager = tag_manager(self.output_dir + '/tags')

    # self.extractor = extractor()
    # self.reference_generator = reference_generator()
    # self.slip_generator = slip_generator()
    # self.tag_generator = tag_generator()
    # self.link_generator = link_generator()

    # self.summary_generator = summary_generator()

    # self.langchain = langchain_client()
    # self.chatgpt = chatgpt_client()

  # def extract(self):
    # Extraction workflow

  # def generate_references(self):  
    # Reference generation workflow

  # def generate_slips(self):
    # Slip generation workflow    

  # def generate_tags(self):
    # Tag generation workflow

  # def generate_links(self):
    # Link generation workflow
    
  def do_task(self, task, source):
    
    return self.manager.do_task(task, source)
    
    # Summary generation workflow
    
  def __init__(self, directory:str):

    self.directory = directory
    
    # Check if slipbox dir exists, create if needed
    if not os.path.exists(directory):
      os.makedirs(directory)
      
      log_and_print(f"Creating empty Slipbox folder {directory}",
                   LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    log_and_print(f"Initializing Slipbox at {directory}",
                   LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    self.manager = sb_slipbox_manager(self)