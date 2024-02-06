# src/sb_slipbox_manager/sb_sources_manager/sb_source/sb_extracts.py

from src.common import *
from src.sb_utils.sb_pdf_to_text import sb_pdf_to_text
from src.sb_utils.sb_img_to_text import sb_img_to_text
import os

class sb_extracts:

  def get_extracts_text_path(self):
    return self._extracts_file_path

  def get_extracts_text_name(self):
    return self._extracts_text_name
    
  def get_extracts_text(self): 

    if not self._extracts_text:
      
      # Get extracts file path
      extracts_path = self.get_extracts_text_path()
      # Check if extracts file exists
         
      if not os.path.exists(extracts_path):
        # File does not exist, extract the text from the PDF, save it, and return that.
        self.update_extracts_text()

      if os.path.exists(extracts_path):
        # Open file for reading
          with open(extracts_path, 'r') as f:
            self._extracts_text = f.read()
        
    return self._extracts_text

  def update_extracts_text(self):
    # This function will extract the JPG or the PDF
    
    filetype = self._source.get_original_file().get_file_type()

    if filetype == ".pdf":
    
      try:
        print(f"Sending command to extract PDF {self._source.get_original_file().get_file_path()} into {self._extracts_file_path}")

        sb_pdf_to_text(self._source.get_original_file().get_file_path(), self._extracts_file_path)
        
      except:
        log_and_print(f"Error with the PDF to Text command",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
                    
    elif filetype == ".jpg":
    
      try:
        print(f"Sending command to extract JPG {self._source.get_original_file().get_file_path()} into {self._extracts_file_path}")

        sb_img_to_text(self._source.get_original_file().get_file_path(), self._extracts_file_path)
        
      except:
        log_and_print(f"Error with the JPG to Text command",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
    else:
      log_and_print(f"Unsupported filetype: {filetype}",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
      
    extracts_path = self.get_extracts_text_path()

    if os.path.exists(extracts_path):
      # Open file for reading
        with open(extracts_path, 'r') as f:
          text = f.read()
          self._extracts_text
          print(f"Newly extracted text success.")

    return
    
  def __init__(self, source):
    self._source = source
    self._extracts_text = None
    self._extracts_file = None
    self._extracts_file_name = f"{self._source.get_source_folder_name()}{DEFAULT_EXTRACTS_FILE_SUFFIX}"
    self._extracts_file_path = self._source.get_source_folder_path()

    # Check Extracts file path 
    self._extracts_file_path = os.path.join(self._extracts_file_path, self._extracts_file_name)

    # Check if extracts file exists
    if os.path.exists(self._extracts_file_path):
           log_and_print(f"Extracts file present from {self._extracts_file_name} for {self._source.get_source_folder_name()}", 
                   LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
  
    else:
      # extracts_file file doesn't exist
  
      log_and_print(f"Extracts file {self._extracts_file_name} not found in {self._source.get_source_folder_name()}",
                   LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    self._extracts_text = self.get_extracts_text()