# src/sb_slipbox_manager/sb_sources_manager/sb_source/sb_original_file.py

import os
from src.common import *
from pathlib import Path

class sb_original_file:

  def __init__(self, source, original_file_source):

    self._source = source
    self._file_path = None
    self._file_name = None
    self._file_obj = None
        
    self._file_path = original_file_source

    # Set private file name property
    self._file_name = os.path.basename(self._file_path)

    # Check if original file exists
    if os.path.exists(self._file_path):

      log_and_print(f"Original file {self._file_name} loaded",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    else:
      # File not found
      log_and_print(f"Original file {self._file_name} not found",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

      self._file_path = None
      self._file_name = None

  def get_file_object(self):
    # Check file path is set
    if not self._file_path:
      raise RuntimeError(f"No file path set for original file at {self.get_source_directory_path()}")

    # Check path exists as a file
    if not os.path.isfile(self._file_path):
      raise FileNotFoundError(f"Original File not found at {self._file_path} for {self.get_source_directory_path()}")

    # Open file handle if not already open
    if not self._file_obj:
      self._file_obj = open(self._file_path, 'rb')
      log_and_print(f"Original file {self._file_path} opened",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    return self._file_obj
  
  def close_file_object(self):

    if self._file_obj:
      self._file_obj.close()
      log_and_print(f"Original file {self._file_path} closed",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
      self._file_obj = None

  def get_file_name(self):
    return self._file_name
    
  def get_file_path(self):
    return self._file_path
    
  def get_file_type(self):
    # Parse the path to get file info
    path = Path(self.get_file_path())

    # Return the suffix which is the file extension
    return path.suffix