# slipbox/src/sb_slipbox_manager/sb_slipbox_manager.py

"""
The sb_slipbox_manager class handles initializing and coordinating all the managers associated with a slipbox instance. When a new slipbox object is created, it initializes an sb_slipbox_manager to manage the various components. The slipbox_manager creates an instance of each manager class to handle sources, slips, tags, references, extracted metadata, and labs.  It provides a simple interface for the slipbox itself to interact with the managers without needing to access them directly.

Key responsibilities:

- Initialize all required slipbox managers 
- Pass calls from slipbox to appropriate manager
- Coordinate workflows between managers
- Abstract slipbox implementation behind simple interface

This enables encapsulating the modular slipbox architecture behind a cohesive facade. The complex internals are wrapped by a simple manager interface. New slipbox capabilities can be added by implementing additional managers, without changing the client usage. The slipbox_manager conducts the underlying modular orchestra.
"""

from src.common import *

from .sb_sources_manager.sb_sources_manager import sb_sources_manager
from .sb_slips_manager.sb_slips_manager import sb_slips_manager
from .sb_tags_manager.sb_tags_manager import sb_tags_manager
from .sb_references_manager.sb_references_manager import sb_references_manager
from .sb_extracted_metadata_manager.sb_extracted_metadata_manager import sb_extracted_metadata_manager
from .sb_labs_manager.sb_labs_manager import sb_labs_manager

class sb_slipbox_manager():

  def do_task(self, task, source):
    
    return self.labs_manager.do_task(task, source)
    
    # Summary generation workflow
    
  def __init__(self, slipbox):
    self.slipbox = slipbox
    
    # Initialize Slipbox Managers
    log_and_print(f"Initializing Slipbox Managers at {self.slipbox.directory}",
                 LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    self.labs_manager = sb_labs_manager(self)
    self.sources_manager = sb_sources_manager(self)
    self.slips_manager = sb_slips_manager(self)
    self.references_manager = sb_references_manager(self)
    self.tags_manager = sb_tags_manager(self)
    self.extracted_metadata_manager = sb_extracted_metadata_manager(self)
    
    log_and_print(f"Slipbox managers initialized", 
                  LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
  def import_files(self, file_paths):
    self.sources_manager.import_files(file_paths)