# src/tag/sb_tag.py

# Import SlipBox’s common functions and constants.
from src.common import *

def sb_tag(inputs, output, *, length=5):
  """Extract key points"""
  
  # Print statement to confirm extraction
  verbose_print(f'Tagging {length} points from {inputs} into {output}', VERBOSITY_LEVELS.INFO)
  
  pass