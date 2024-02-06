# src/utils/sb_pdf_utils.py

# Import SlipBox’s common functions and constants.
from src.common import *

def separate_pages(page_num):
  """Format page separator string with page number.

  Args:
    page_num (int): Page number to include in separator 

  Returns:
    str: Formatted page separator string

  Raises:
    ValueError: If page_num is not an integer

  """

  # Validate page number
  if not isinstance(page_num, int):
    raise ValueError('Page number must be an integer')

  if page_num == 1:
    # No newlines for first page
    return f"===== Page {page_num} =====\n"
  else:
    # Add newlines for other pages
    return f"\n\n\n===== Page {page_num} =====\n"

  return separator