#slipbox.py

import argparse  
import os
import sys

# Import SlipBox’s common functions and constants.
from src.common import *

# Import functions for the main commands.
from src.sb_extract import sb_extract 
from src.sb_link import sb_link
from src.sb_utils import sb_pdf_to_text
from src.sb_summarize import sb_summarize
from src.sb_tag import sb_tag

# Import functions for the file importer.
import src.sb_import

# Import functions for the file importer.
import src.sb_slipbox

# Main function
def main():

  # Create argument parser object
  parser = argparse.ArgumentParser(description='Slipbox research tool')

  # Add argument to specify command  
  parser.add_argument('command', choices=['extract', 'summarize', 'tag', 'link', 'pdf_to_text'])

  # Add argument to allow multiple input files/dirs
  parser.add_argument('-i', '--inputs', nargs='*', type=str,
                      help='Input files and folders. (Default: inbox in slipbox folder). This argument is optional. If left blank, it will default to the DEFAULT_INPUT_PATH.', 
                      default=[DEFAULT_INPUT_PATH])

  parser.add_argument('--extensions', nargs='*', default=ALLOWED_EXTENSIONS, 
                    help='Allowed file extensions')	

  # Add argument to allow multiple input files/dirs
  parser.add_argument('-r', '--recursive', action='store_true', help='Recursively process directories')
  
  parser.add_argument('-s', '--slipbox_dir', type=str, 
                      help='Slipbox output path (default: slipbox folder under home directory)', 
                      default=DEFAULT_SLIPBOX_PATH)

  # Add argument to specify number of extracts
  # parser.add_argument('-l', '--length', type=int, default=5, help='Number of extracts to generate per source')

  # Add argument to specify summary length
  # parser.add_argument('-s', '--size', type=int, default=100, help='Approximate size of the summary in words')
  
  # Set default verbosity level
  # The strings for the VERBOSITY_LEVELS are pulled from the names of the keys.
  verbosity_choices = list(VERBOSITY_LEVELS._member_map_.keys()) + ["0", "1", "2"] 
  #, "2", "3", "4", "5" 

  parser.add_argument('-v', '--verbosity', type=str,  
                   choices=verbosity_choices, 
                   nargs="?",
                   help='Verbosity level')

  # Set default log level
  # The strings for the VERBOSITY_LEVELS are pulled from the names of the keys.
  log_level_choices = list(LOG_LEVELS._member_map_.keys()) + ["0", "1", "2", "3", "4", "5", "6"]

  parser.add_argument('-l', '--loglevel', type=str,  
                   choices=log_level_choices,
                   nargs="?",
                   help='Log level')

  # Set default debug level
  # The strings for the DEBUG_LEVELS are pulled from the names of the keys.
  debug_level_choices = list(DEBUG_LEVELS._member_map_.keys()) + ["0", "1"]

  parser.add_argument('-d', '--debuglevel', type=str,  
                   choices=debug_level_choices,
                   nargs="?",
                   help='Debug level')

  # Parse args 
  args = parser.parse_args()

  # Setup the verbosity_levelvalue, if there is nothing passed.
  if '-v' in sys.argv and args.verbosity is None:
    args.verbosity = "ERROR"
  if not args.verbosity:
    args.verbosity = "NONE"
  
  try:
    configure_verbosity(str(args.verbosity))
  except ValueError as e:
    print(f"Error configuring verbosity level: {e}")
    close_and_exit(1)

  # Setup the default log_level, if there is nothing passed.
  if '-l' in sys.argv and args.loglevel is None:
    args.loglevel = "ERROR"
  if not args.loglevel:
    args.loglevel = "NONE"
      
  try:
    configure_log_level(str(args.loglevel))
  except ValueError as e:
    print(f"Error configuring log level: {e}")
    close_and_exit(1)

  # Setup the debug level
  if '-d' in sys.argv and args.debuglevel is None:
    args.debuglevel = "ACTIVE"
  if not args.debuglevel:
    args.debuglevel = "INACTIVE"
      
  try:
    configure_debug_level(str(args.debuglevel))
  except ValueError as e:
    print(f"Error configuring debug level: {e}")
    close_and_exit(1)

  # Check if no arguments, and call relevant function
  
  if len(sys.argv) == 1:
    verbose_print("No args",VERBOSITY_LEVELS.INFO)
    parser.print_help() 
    close_and_exit(1)
  
  from langchain_community.llms import Ollama
  
  # Initialize Slipbox
  slipbox_dir = args.slipbox_dir
  slipbox = src.sb_slipbox.sb_slipbox(slipbox_dir)
    
  # Generate slips

  # Initialize file importer
  # Create importer instance with all inputs and recursive flag
  inputs = args.inputs
  recursive = args.recursive
  
  importer = src.sb_import.file_importer(inputs, args.extensions, recursive=args.recursive)
  
  slipbox.import_files(importer.file_paths)
  
  
  # Check command and call relevant function
  """
  if args.command == 'cleanup_ocr':
    sb_extract.sb_extract(args.inputs, args.output_path, length=args.length)


  elif args.command == 'link':
    sb_link.sb_link(args.inputs, args.output_path)
    
  elif args.command == 'pdf_to_text':
    sb_pdf_to_text.sb_pdf_to_text(args.inputs[0], args.output_path)
    
  elif args.command == 'summarize':
    sb_summarize.sb_summarize(args.inputs[0], args.output_path, size=args.size)

  elif args.command == 'tag':
    sb_tag.sb_tag(args.inputs, args.output_path) 
  """
  
  close_and_exit(0)
  
def close_and_exit(exit_code):
  close_log()
  sys.exit(exit_code)
  
# Check if run as script
if __name__ == '__main__':
  
  # Call main function
  main()