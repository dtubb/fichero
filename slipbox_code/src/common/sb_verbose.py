#src/common/sb_verbose.py 

import sys
import itertools

# Import SlipBox’s common functions and constants.
from src.common import *

"""
Provides a verboe function to handle verbose logs to the CLI based
on verbsosity levels.

The global verbsosity level is an ENUM, defined in sb_constants.py higher values enabling
more detailed verbsosity reports.

Usage:

  1. Configure verbsosity level

  2. Import and call print_verbsosity() to print messages conditionally  

     based on verbsosity level.

The goal is to consolidate verbsosity in this module
based on a configurable verbsosity level.
"""

# Default verbosity level
verbosity = VERBOSITY_LEVELS.NONE

def get_verbosity():
  """
  Get the current global verbosity level

  Returns:
    verbosity (Verbosity enum member):
      The current verbosity level 
  """
  
  return verbosity

def get_verbosity_level_name():
  """
  Get the name of the current verbosity level

  Returns:
    name (string):
      The name of the current verbosity level (e.g. "INFO")
  """

  # Get verbosity level enum member
  member = get_verbosity()

  # Get all level names
  names = list(VERBOSITY_LEVELS._member_map_.keys())

  # Get name from member index
  return names[list(VERBOSITY_LEVELS).index(member)]
   
def configure_verbosity(verbosity_str):
  """
  Configure the global verbosity level

  Args:
    verbosity_str (string):
      The verbosity level name or number

  Raises:  
    ValueError if level is invalid
  """

  # Generate valid levels
  valid_levels = list(VERBOSITY_LEVELS._member_map_.keys())

  # Generate valid indexes
  int_levels = list(range(len(valid_levels)))

  # Combine into one list 
  valid_values = valid_levels + [str(i) for i in int_levels]

  # Set and validate input
  value = str(verbosity_str).upper()

  if value not in valid_values:
    raise ValueError(f"Invalid verbsoity level: {value} is not valid")

  if value in VERBOSITY_LEVELS._member_map_:
    member = VERBOSITY_LEVELS[value]
  else: 
    # Convert value to int before using as index
    value_int = int(value)

    try:
      member = list(VERBOSITY_LEVELS)[value_int]
    except IndexError:  
      raise ValueError(f"{value} is invalid")

  # Lookup or convert level
  set_verbosity(member)
  
def set_verbosity(level):

  """
  Set the global verbosity level

  Args:
    level (Verbosity enum member)

  Raises:  
    ValueError if invalid
  """
  
  # Validate level  
  members = list(VERBOSITY_LEVELS)

  if level not in members:
    raise ValueError(f"Verbsoity level {level} out of range")  

  # Set global level
  global verbosity 
  verbosity = level
  level_name = get_verbosity_level_name()

  # Notify of change  
  verbose_print(f"Verbosity level set to: {level_name}.", VERBOSITY_LEVELS.ERROR)

def verbose_print(message, level):
  """
  Print message if verbosity meets level

  Args:
    message: message to print
    level: minimum required level
  """

  if level == VERBOSITY_LEVELS.NONE:
    # Print nonthing
    pass
   
  elif level == VERBOSITY_LEVELS.ERROR: 
    # Print errors
    pass
  
  """
  elif level == VERBOSITY_LEVELS.INFO:
    # Standard prints
    pass
  
  elif level == VERBOSITY_LEVELS.WARNING:
    # Print warnings
    pass
  
  elif level == VERBOSITY_LEVELS.ERROR:
     # Print critical errors
    pass
  """
  
  # Check against global level
  members = list(VERBOSITY_LEVELS)

  if members.index(verbosity) >= members.index(level):
    print(message, flush=True)