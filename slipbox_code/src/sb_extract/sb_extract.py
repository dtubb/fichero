# src/extract/sb_extract.py

# Import SlipBox’s common functions and constants.
from src.common import *

def sb_extract(inputs, output, *, length=5):
  """Extract key points"""
  
  # Print statement to confirm extraction
  verbose_print(f'Extracting {length} points from {inputs} into {output}', VERBOSITY_LEVELS.INFO)
  
  pass