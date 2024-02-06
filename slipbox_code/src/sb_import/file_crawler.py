#src/sb_import/file_crawler.py

# Import SlipBox's common functions and constants. 
from src.common import *

import os
from fnmatch import fnmatch

class file_crawler:

  # Crawls a list of file/folder paths recursively to find all valid files
  
  def crawl(self, paths, all_inputs, allowed_extensions):

    glob_patterns = []

    for input in all_inputs:
      if "*" in input or "?" in input:
        glob_patterns.append(input)
        
    # Initialize empty list to hold discovered file paths  
    allowed_files = []

    # Loop through each input path
    for path in paths:
    
      # Check if path matches any pattern in all_inputs 
      if any(fnmatch(path, pattern) for pattern in all_inputs):
      
        # If it's a file, check extension and add it if allowed
        if os.path.isfile(path):
          
          filename, ext = os.path.splitext(path)
          
          if ext in allowed_extensions:

            allowed_files.append(path)

            # Log discovered file        
            log(f"Discovered file: {path}", LOG_LEVELS.INFO)
            verbose_print(f"Discovered file: {path}", VERBOSITY_LEVELS.INFO)

        # If it's a directory, walk recursively
        elif os.path.isdir(path):
        
          # Traverse directory tree with os.walk()
          for root, dirs, filenames in os.walk(path):
          
            # Loop through each filename  
            for filename in filenames:

              # Construct full file path
              file_path = os.path.join(root, filename)

              # Check filename does not start with dot
              if not filename.startswith('.'):
                
                # Check file extension
                filename, ext = os.path.splitext(file_path)
                
                if ext in allowed_extensions:
                
                  # Add allowed file to results
                  allowed_files.append(file_path)
                  
                  # Log discovered file  
                  log(f"Discovered file: {file_path}", LOG_LEVELS.INFO)
                  verbose_print(f"Discovered file: {file_path}", VERBOSITY_LEVELS.INFO)

    # Log allowed files
    log(f"Crawled allowed files: {allowed_files}", LOG_LEVELS.INFO)
    verbose_print(f"Crawled allowed files: {allowed_files}", VERBOSITY_LEVELS.INFO)
    
        # Additional logging
    log(f"Allowed extensions: {allowed_extensions}", LOG_LEVELS.INFO)
    verbose_print(f"Allowed extensions: {allowed_extensions}", VERBOSITY_LEVELS.INFO)
    
    # Return allowed files
    return allowed_files