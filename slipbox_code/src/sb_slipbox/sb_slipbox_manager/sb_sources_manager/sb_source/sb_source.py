# src/sb_slipbox_manager/sb_sources_manager/sb_source/sb_source

from src.common import *
from .sb_catalogue import sb_catalogue
from .sb_extracts import sb_extracts
from .sb_extracts_ocr_cleaned import sb_extracts_ocr_cleaned
from .sb_extracted_metadata import sb_extracted_metadata
from .sb_original_file import sb_original_file

import yaml
import shutil 
import os
import datetime

class sb_source:

  def import_original_file(self, import_file_path, source_id):
    # Get base filename without extension
    file_name = os.path.basename(import_file_path)  
    name, ext = os.path.splitext(file_name)
    
    # Set ID based on the passed variable
    self.set_id(source_id)
    self.set_name(name)

    # Set file name  
    # Construct file name with ID  

    self.set_source_md_file_name(file_name)
    # Set folder name using base name only

    folder_name = f"{source_id}-{name}"
    self.set_source_folder_name(folder_name)

    # Set folder path 
    source_dir = self.get_source_directory_path()
    source_folder = self.get_source_folder_name()

    source_folder_path = os.path.join(source_dir, source_folder)
    self.set_source_folder_path(source_folder_path)
    
    # Get destination directory
    dest_dir = self.get_source_folder_path()  

    # Check if directory exists
    if os.path.exists(dest_dir):
      pass
    else:
      os.makedirs(dest_dir)
  
    # Copy file to destination  
    shutil.copy(import_file_path, dest_dir)

    # Get full filename  
    fname = os.path.basename(import_file_path)

    # Split name and extension
    name, ext = os.path.splitext(fname)

    # Construct new name with ID  
    new_name = f"{source_id}-{name}{ext}"

    # Build renamed path
    renamed_path = os.path.join(dest_dir, new_name)  

    # Rename the file
    os.rename(os.path.join(dest_dir, fname), renamed_path)
    
    # Get renamed path after importing
    original_file_source = renamed_path  

    # Create sb_original_file instance, and set it in the setter.
    original_file = sb_original_file(self, original_file_source)
    self.set_original_file(original_file)

    # Generate YAML
    yaml_data = self._generate_source_md_yaml()

    # Save YAML file
    self.update_source_md_yaml(yaml_data) 

    # Load properties from YAML into object  
    self.load_source_md_yaml(yaml_data)
    log_and_print(f"Generated YAML: {yaml_data}", LOG_LEVELS.DEBUG, VERBOSITY_LEVELS.DEBUG) 
    
    self._extracts = sb_extracts(self) 
    extracts_text = self._extracts.get_extracts_text()
    log_and_print(f"Extracts Text: {extracts_text}", LOG_LEVELS.DEBUG, VERBOSITY_LEVELS.DEBUG) 


  # Source_folder_name is the name of the source folder Folder, e.g '123-research-paper'
  def get_source_folder_name(self):
    return self._source_folder_name
  
  def set_source_folder_name(self, source_folder_name):
    self._source_folder_name = source_folder_name

  # Source_folder_path is the path to the source folder Folder, e.g '\slipbox\sources\123-research-paper'
  def get_source_folder_path(self):
    return self._source_folder_path

  def set_source_folder_path(self, source_folder_path):
    self._source_folder_path = source_folder_path

  # ID is the ID of the source, e.g '123'
  def get_id(self):
    return self._id
  
  def set_id(self, id):
    self._id = int(id) 

  # Name is the Name of the source, e.g 'research-paper'
  def get_name(self):  
    return self._name

  def set_name(self, name):
    self._name = name

  #  # Source_folder_name is the filename of the source file, e.g '123-research-paper'
  #  def get_source_folder_name(self):
  #    return self._source_folder_name

  # def set_source_folder_name(self, folder):
  #   self._source_folder_name = folder
    
  # Name is the filename of the source file, e.g '123-research-paper-source.md'
  def get_source_md_file_name(self):
     # Set default if None
     if self._source_md_file_name is None:
       self._source_md_file_name = ""

     # Append extension if needed
     if not self._source_md_file_name.endswith(DEFAULT_SOURCES_FILE_EXTENSION):
       name = os.path.splitext(self._source_md_file_name)[0]
       return name + DEFAULT_SOURCES_FILE_EXTENSION

     return self._source_md_file_name
        
  def set_source_md_file_name(self, filename):
    # Strip any extension
    name = os.path.splitext(filename)[0]
  
    # Add .md extension
    name += DEFAULT_SOURCES_FILE_EXTENSION
  
    if not filename.endswith(DEFAULT_SOURCES_FILE_EXTENSION):
       filename += DEFAULT_SOURCES_FILE_EXTENSION

    # Set property
    self._source_md_file_name = name

  # Name is the filename of the source file, e.g '123-research-paper'
  def get_source_md_file_path(self):

    # Check if path already set
    if self._source_md_file_path:
      return self._source_md_file_path

    # Path not set, construct it

    # Get folder path
    folder_path = self.get_source_folder_path()

    # Construct filename
    filename = f"{self.get_source_folder_name()}{DEFAULT_SOURCES_FILE_EXTENSION}"

    # Join folder path and filename
    full_path = os.path.join(folder_path, filename)

    return full_path

  def set_source_md_file_path(self, path):
    self._source_md_file_path = path
    
  # Direcory is the path to the sources foler directory, e.g '123-research-paper'
  def get_source_directory_path(self):
    return self._source_directory_path

  def set_source_directory_path(self, path):
    self._source_directory_path = path

  # Generate new metadata 
  def _generate_source_md_yaml(self):
    yaml_data = {
        'source_id': self.get_id(),
        'source_name': self.get_name(),
        'source_folder_name': self.get_source_folder_name(),
        'source_md_file_name': self.get_source_md_file_name(),
        'source_md_file_path': self.get_source_md_file_path(),
        'source_folder_path': self.get_source_folder_path(), 
        'original_filename': self.get_original_file().get_file_name(),
        'original_filepath': self.get_original_file().get_file_path(),
    }

        #'created_at': datetime.datetime.now(),
        #'modified_at': datetime.datetime.now(),
        #'added_at': datetime.datetime.now()

    return yaml_data

  def load_source_md_yaml(self, yaml_data):

    if yaml_data: 
      
      self.set_id(yaml_data['source_id'])
      self.set_name(yaml_data['source_name'])
      self.set_source_folder_name(yaml_data['source_folder_name'])
      self.set_source_md_file_name(yaml_data['source_md_file_name'])
      self.set_source_md_file_path(yaml_data['source_md_file_path'])
      self.set_source_folder_path(yaml_data['source_folder_path'])
    
      original_file = sb_original_file(self, yaml_data['original_filepath'])
      self.set_original_file(original_file)

    else:
      # No YAML yet, skip loading
      pass
      
  # Load existing metadata
  
  def get_source_md_yaml(self):
    yaml_data = None

    if os.path.exists(self.get_source_md_file_path()):
      with open(self.get_source_md_file_path()) as f:
        try:
          yaml_data = yaml.safe_load(f)
          log_and_print(f"Succes loading YAML: {yaml_data}", LOG_LEVELS.ERROR, VERBOSITY_LEVELS.ERROR)

        except yaml.YAMLError as e:
          log_and_print(f"Error loading YAML: {e}", LOG_LEVELS.ERROR, VERBOSITY_LEVELS.ERROR)

    if not yaml_data:  
      yaml_data = yaml.safe_load(self._generate_source_md_yaml())

    return yaml_data

  def _open_source_md_file_rw(self):
    filepath = self.get_source_md_file_path()

    # Check if file exists
    if not os.path.exists(filepath):
       # If not, create the empty file
      open(filepath, "w").close()  
      log_and_print(f"Creating source-md file at {filepath}", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    return open(filepath, "r+")
    
  def _save_source_file(self, md_data):
     # Write to file 
     f = self._open_source_md_file_rw()  
     f.write(yaml.dump(md_data))
     f.close
     
  def update_source_md_yaml(self, new_md_data):
      self._save_source_file(new_md_data) 
      
  # Getter and Setter for Original file
  def get_original_file(self):
    return self._original_file  

  def set_original_file(self, original_file):
    self._original_file = original_file

  def get_extracted_ocr_cleaned_text(self):
    return self._extracts_ocr_cleaned.get_extracts_ocr_cleaned_text()
    

  def get_extracts_text(self):
    return self._extracts.get_extracts_text()
    
  def __init__(self, source_manager, source_folder_path, source_direcrtory_path, load=True):
    
    # Define Privcate Properties
    self.source_manager = source_manager
    self._source_folder_path = source_folder_path
    self._source_directory_path = source_direcrtory_path
    
    #ID - Unique identifier, like '123'
    self._id = None

    # Name - Human readable name extracted from metadata, does NOT contain ID. Just name like 'My Research on AI'
    self._name = None

    # Folder name - Contains ID, like '123-research-paper'
    self._source_folder_name = None

    # Source filename - Matches folder name, so also contains ID '123-research-paper'
    self._source_md_file_name = None

    # Source path - Matches folder name, so also contains ID '123-research-paper\123-research-paper.md'
    self._source_md_file_path = None
    
    self._original_file = None
    self._extracts = None
    self._extracts_ocr_cleaned = None
    self._extracted_metadata = None
    self._catalogue = None

    if load:
      source_folder_name = os.path.basename(self._source_folder_path)
      self.set_source_folder_name(source_folder_name)
      
      log_and_print(f"\nInitializing loading {self.get_source_folder_name()} source", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

      if os.path.exists(self.get_source_md_file_path()): 
         log_and_print(f"Source file found at {self.get_source_md_file_path()}", 
                      LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
     
      else:
        self.set_source_md_file_path(None)
        log_and_print(f"No -source.md file found in {self.get_source_md_file_path()}",  
                      LOG_LEVELS.WARNING, VERBOSITY_LEVELS.WARNING)
        
        raise source_md_file_validation_error(f"{self.get_source_md_file_path()} file does not exist")
    
      # Check if file is empty
      if os.path.getsize(self.get_source_md_file_path()) == 0:
        # File is empty, invalid source 
        log_and_print(f"Empty -source.md file at {self.get_source_md_file_path()}",  
                      LOG_LEVELS.WARNING, VERBOSITY_LEVELS.WARNING)

        raise source_md_file_validation_error(f"{self.get_source_md_file_path()} file empty")
        
      # If so, load YAML
      yaml_data = self.get_source_md_yaml()
    
      # Load properties from YAML
      self.load_source_md_yaml(yaml_data)
      
      log_and_print(f"Loaded YAML: {yaml_data}", LOG_LEVELS.DEBUG, VERBOSITY_LEVELS.DEBUG) 

      # Create extracts object
      self._extracts = sb_extracts(self) 
      if self._extracts is None:
        log_and_print(f"Extracts text file is empty.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO) 

      # Create extracts ocr-object object, and then print the extract-ocr-cleanup text.
      self._extracts_ocr_cleaned = sb_extracts_ocr_cleaned(self) 
      if self._extracts_ocr_cleaned is None:
        log_and_print(f"Extracts-OCR-Cleanup file is empty.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO) 

      # Create extracts ocr-object object, and then print the extract-ocr-cleanup text.
      self._extracted_metadata = sb_extracted_metadata(self) 
      if self._extracted_metadata is None:
        log_and_print(f"Extracted Metadata is empty.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO) 


      # self._catalogue = sb_catalogue(self, self.get_source_folder_name())
      # self._extracted_metadata = sb_extracted_metadata(self, self.get_source_folder_name())
      # self.extracted_metadata = sb_extracted_metadata(self, self._source_folder_path)

      log_and_print(f"Source {self.get_source_folder_name()} loaded", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    else:
      log_and_print(f"New empty source created.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
