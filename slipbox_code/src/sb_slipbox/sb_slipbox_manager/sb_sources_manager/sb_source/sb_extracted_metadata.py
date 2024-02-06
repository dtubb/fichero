# src/sb_slipbox_manager/sb_sources_manager/sb_source/sb_extracted_metadata.py

from src.common import *
from src.sb_utils.sb_pdf_to_text import sb_pdf_to_text
from src.sb_utils.sb_img_to_text import sb_img_to_text
import os

class sb_extracted_metadata:

  def get_extracted_metadata_text_path(self):
    return self._extracted_metadata_file_path

  def get_extracted_metadata_text_name(self):
    return self._extracted_metadata_text_name
    
  def get_extracted_metadata_text(self): 

    if not self._extracted_metadata_text:
      
      # Get extracts file path
      extracted_metadata_path = self.get_extracted_metadata_text_path()
      # Check if extracts file exists
         
      if not os.path.exists(extracted_metadata_path):
        # File does not exist, extract the text from the PDF, save it, and return that.
        self.update_extracted_metadata_text()

      if os.path.exists(extracted_metadata_path):
        # Open file for reading
          with open(extracted_metadata_path, 'r') as f:
            self._extracted_metadata_text = f.read()
                
    return self._extracted_metadata_text

  def update_extracted_metadata_text(self):

    extracted_ocr_cleaned_text = self._source.get_extracted_ocr_cleaned_text()
    
    json_extracted_metadata = self._source.source_manager.slipbox_manager.do_task(
      "Please extract the METADATA from this SOURCE.",
      extracted_ocr_cleaned_text
    )
    extracted_metadata = ""
    
    for key, value in json_extracted_metadata.items():
      extracted_metadata = extracted_metadata+f"{value}\n"
          
    print("""=============
{extracted_metadata}
=============
""")
    
    # Get file path
    extracted_metadata_path = self.get_extracted_metadata_text_path()

    # Write test text to file
    with open(extracted_metadata_path, "w") as f:
      f.write(extracted_metadata)

    print("Updated the extracted_metadata text file with the text.")

    # Update internal variable
    self._extracted_metadata_text = extracted_metadata
  
  def __init__(self, source):
  
     self._source = source
     self._extracted_metadata_text = None
     self._extracted_metadata_file = None
     self._extracted_metadata_file_name = f"{self._source.get_source_folder_name()}{DEFAULT_EXTRACTED_METADATA_FILE_SUFFIX}"
     self._extracted_metadata_file_path = self._source.get_source_folder_path()
     
     # Check Extracts file path 
     self._extracted_metadata_file_path = os.path.join(self._extracted_metadata_file_path, self._extracted_metadata_file_name)

     # Check if extracts file exists
     if os.path.exists(self._extracted_metadata_file_path):
            log_and_print(f"Extracts-Metadata file present from {self._extracted_metadata_file_name} for {self._source.get_source_folder_name()}", 
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
       
     else:
       # extracts_file file doesn't exist
       
       log_and_print(f"Extracts-Metadata file not present for {self._extracted_metadata_file_name} not found in {self._source.get_source_folder_name()}",
                    LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

     self._extracted_metadata_text = self.get_extracted_metadata_text()
     print(f"Loaded from file: {self._extracted_metadata_text}")