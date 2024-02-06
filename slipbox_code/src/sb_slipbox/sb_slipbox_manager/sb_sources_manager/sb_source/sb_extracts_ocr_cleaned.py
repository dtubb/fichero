# src/sb_slipbox_manager/sb_sources_manager/sb_source/sb_extracts_ocr_cleaned.py

from src.common import *
from src.sb_utils.sb_pdf_to_text import sb_pdf_to_text
from src.sb_utils.sb_img_to_text import sb_img_to_text
import os

class sb_extracts_ocr_cleaned:

  def get_extracts_ocr_cleaned_text_path(self):
    return self._extracts_ocr_cleaned_file_path

  def get_extracts_ocr_cleaned_text_name(self):
    return self._extracts_ocr_cleaned_text_name
    
  def get_extracts_ocr_cleaned_text(self): 

    if not self._extracts_ocr_cleaned_text:
      
      # Get extracts file path
      extracts_ocr_cleaned_path = self.get_extracts_ocr_cleaned_text_path()
      # Check if extracts file exists
         
      if not os.path.exists(extracts_ocr_cleaned_path):
        # File does not exist, extract the text from the PDF, save it, and return that.
        self.update_extracts_ocr_cleaned_text()

      if os.path.exists(extracts_ocr_cleaned_path):
        # Open file for reading
          with open(extracts_ocr_cleaned_path, 'r') as f:
            self._extracts_ocr_cleaned_text = f.read()
                
    return self._extracts_ocr_cleaned_text

  def update_extracts_ocr_cleaned_text(self):

    extracts_text = self._source.get_extracts_text()
    
    json_cleaned_text = self._source.source_manager.slipbox_manager.do_task(
      "Please clean the the OCR in the SOURCE",
      extracts_text
    )
    cleaned_text = ""
    
    for key, value in json_cleaned_text.items():
      cleaned_text = cleaned_text+f"{value}\n"
          
    print("""=============
{cleaned_text}
=============
""")
    
    # Get file path
    extracts_ocr_cleaned_path = self.get_extracts_ocr_cleaned_text_path()

    # Write test text to file
    with open(extracts_ocr_cleaned_path, "w") as f:
      f.write(cleaned_text)

    print("Updated extracts_ocr_cleaned text file with test text.")

    # Update internal variable
    self._extracts_ocr_cleaned_text = cleaned_text
  
  def __init__(self, source):
  
     self._source = source
     self._extracts_ocr_cleaned_text = None
     self._extracts_ocr_cleaned_file = None
     self._extracts_ocr_cleaned_file_name = f"{self._source.get_source_folder_name()}{DEFAULT_EXTRACTS_OCR_CLEANED_FILE_SUFFIX}"
     self._extracts_ocr_cleaned_file_path = self._source.get_source_folder_path()
     
     # Check Extracts file path 
     self._extracts_ocr_cleaned_file_path = os.path.join(self._extracts_ocr_cleaned_file_path, self._extracts_ocr_cleaned_file_name)

     # Check if extracts file exists
     if os.path.exists(self._extracts_ocr_cleaned_file_path):
            log_and_print(f"Extracts-OCR-Cleaned file present from {self._extracts_ocr_cleaned_file_name} for {self._source.get_source_folder_name()}", 
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
       
     else:
       # extracts_file file doesn't exist
       
       log_and_print(f"Extracts-OCR-Cleaned file not present for {self._extracts_ocr_cleaned_file_name} not found in {self._source.get_source_folder_name()}",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

     self._extracts_ocr_cleaned_text = self.get_extracts_ocr_cleaned_text()
     print(f"Loaded from file: {self._extracts_ocr_cleaned_text}")