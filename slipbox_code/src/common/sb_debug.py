#src/common/sb_debug.py 

import sys

# Import SlipBox’s common functions and constants.
from src.common import *

"""
Provides a debug function to disable code, based on debug level. Debug is either on or off.

The global debug level is an ENUM, defined in sb_constants.py higher values enabling debug mode.

Usage:

  1. Configure debug level

  2. Import and call debug() to debug messages conditionally  

     based on debug level.

The goal is to consolidate all debuging switching this module
based on a configurable debug level.
"""

# Default debug level
# Debug_LEVELS defined in constants.py
debug_level = DEBUG_LEVELS.INACTIVE

def get_debug_level():
  """
  Get the current global debug level

  Returns:
    debug_level (DEBUG_LEVEL enum member): 
      The current debug level enum member
  """
  
  return debug_level

def get_debug_level_name():
  """
  Get the name of the current debug level

  Returns:
    name (string):
      The name of the current debug level (e.g. "ERROR")
  """

  # Get the debug level Enum member 
  member = get_debug_level()  

  # Get list of all level names from _member_map_
  names = list(DEBUG_LEVELS._member_map_.keys())

  # Index into names with the member's position
  # Returns correct name string
  return names[list(DEBUG_LEVELS).index(member)]
  
def configure_debug_level(level_str):

  """
  Configure the global debug level

  Args:
    level_str (string): 
      The debug level name or number  

  Raises:
    ValueError if level is invalid
  """

  # Get all valid level names  
  valid_levels = list(DEBUG_LEVELS._member_map_.keys())   

  # Get indexes of all valid levels
  int_levels = list(range(len(valid_levels)))    

  # Combine names and indexes
  valid_values = valid_levels + [str(i) for i in int_levels]

  # Standardize input
  level_str = level_str.upper()

  # Validate input 
  if level_str not in valid_values:
    raise ValueError(f"Invalid debug level: {level_str}")

  # Lookup level directly from name
  if level_str in DEBUG_LEVELS._member_map_:
    member = DEBUG_LEVELS[level_str]

  else:

    # Try parsing level as int
    try:  

      value_int = int(level_str)

      # Get level from int
      member = list(DEBUG_LEVELS)[value_int]   

    except IndexError:

      # Raise if int out of range
      raise ValueError(f"{level_str} is invalid")      

  # Set global level   
  set_debug_level(member)

def set_debug_level(level):

  """
  Set the global debug level

  Args:
    level (DEBUG_LEVEL): 
      The debug level Enum member

  Raises:
    ValueError if level is invalid
  """

  # Get list of valid debug levels
  members = list(DEBUG_LEVELS)  

  # Check if level is valid
  if level not in members:
    raise ValueError(f"Debug level {level} out of range")
    
  # Set global state   
  global debug_level
  debug_level = level

  # Inform of change
  verbose_print(f"Debug level set to: {get_debug_level_name()}", 
               VERBOSITY_LEVELS.INFO)
               
def is_debugging():

  """
  Debug a message based on level.

  Args:
    message: message to debug
    level: minimum level required 
  """
  
  if level == DEBUG_LEVELS.OFF:
    # handle PROCESS level debugging
    return FALSE

  elif level == DEBUG_LEVELS.ON:  
    # handle IO level debugging
    return TRUE