#src/common/sb_log.py 

import sys
import logging

# Import SlipBox’s common functions and constants.
from src.common import *
"""
Provides a logging function to handle structured logging based
on log levels.

The global log level is an ENUM, defined in sb_constants.py higher values enabling
more detailed logs.

Usage:

  1. Configure log level

  2. Import and call log() to log messages conditionally  

     based on log level.

The goal is to consolidate all logging in this module
based on a configurable log level.
"""

# Default log level
# LOG_LEVELS defined in constants.py
log_level = LOG_LEVELS.NONE

# Default log file
LOG_FILE = 'slipbox.log'

# Create Logger
logger = None
formatter = None

def get_log_level():
  """
  Get the current global log level

  Returns:
    log_level (LOG_LEVEL enum member): 
      The current log level enum member
  """
  
  return log_level

def get_logger_level():

  log_level = get_log_level()

  if log_level == LogLevel.NONE:
    return NOTSET

  elif log_level == LogLevel.FATAL:
    return FATAL
    
  elif log_level == LogLevel.CRITICAL:
    return CRITICAL

  elif log_level == LogLevel.ERROR:
    return ERROR
    
  elif log_level == LogLevel.WARNING:  
    return WARNING

  elif log_level == LogLevel.INFO:
    return INFO
    
  elif log_level == LogLevel.DEBUG:
    return DEBUG

def get_log_level_name():
  """
  Get the name of the current log level

  Returns:
    name (string):
      The name of the current log level (e.g. "ERROR")
  """

  # Get the log level Enum member 
  member = get_log_level()  

  # Get list of all level names from _member_map_
  names = list(LOG_LEVELS._member_map_.keys())

  # Index into names with the member's position
  # Returns correct name string
  return names[list(LOG_LEVELS).index(member)]
  
def configure_log_level(level_str):

  """
  Configure the global log level

  Args:
    level_str (string): 
      The log level name or number  

  Raises:
    ValueError if level is invalid
  """

  # Get all valid level names  
  valid_levels = list(LOG_LEVELS._member_map_.keys())   

  # Get indexes of all valid levels
  int_levels = list(range(len(valid_levels)))    

  # Combine names and indexes
  valid_values = valid_levels + [str(i) for i in int_levels]

  # Standardize input
  level_str = str(level_str).upper()

  # Validate input 
  if level_str not in valid_values:
    raise ValueError(f"Invalid log level: {level_str}")

  # Lookup level directly from name
  if level_str in LOG_LEVELS._member_map_:
    member = LOG_LEVELS[level_str]

  else:

    # Try parsing level as int
    try:  

      value_int = int(level_str)

      # Get level from int
      member = list(LOG_LEVELS)[value_int]   

    except IndexError:

      # Raise if int out of range
      raise ValueError(f"{level_str} is invalid")      

  # Set global level   
  set_log_level(member)
  
  # Create the logger
  
  # Checks the logger, if its open, closes it.
  global logger
  global formatter
  global LOG_FILE
  
  if logger:
    logging.shutdown()

  logger = logging.getLogger(__name__)
  logger.setLevel(logging.DEBUG)

  handler = logging.FileHandler(LOG_FILE)
  handler.setLevel(logging.DEBUG)

  formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')

  handler.setFormatter(formatter)

  logger.addHandler(handler)

def set_log_level(level):

  """
  Set the global log level

  Args:
    level (LOG_LEVEL): 
      The log level Enum member

  Raises:
    ValueError if level is invalid
  """

  # Get list of valid log levels
  members = list(LOG_LEVELS)  

  # Check if level is valid
  if level not in members:
    raise ValueError(f"Log level {level} out of range")
    
  # Set global state   
  global log_level
  log_level = level

  # Inform of change
  verbose_print(f"Log level set to: {get_log_level_name()}", 
               VERBOSITY_LEVELS.INFO)
               
def log(message, level):
  global logger
  global formatter
  global LOG_FILE
  
  """
  Log a message based on level.

  Args:
    message: message to log
    level: minimum level required 
  """
  
  # Get log level indexes  
  members = list(LOG_LEVELS)   

  # Check if level meets global threshold. If it doens't, exit without logging. Otherwise, go and log.
  if members.index(log_level) < members.index(level):
    return

  if level == LOG_LEVELS.NONE:
    pass
    
  elif level == LOG_LEVELS.FATAL:
    logger.fatal(message)

  elif level == LOG_LEVELS.CRITICAL:
    logger.critical(message)

  elif level == LOG_LEVELS.ERROR:
    logger.error(message)
    
  elif level == LOG_LEVELS.WARNING:
    logger.warning(message)

  elif level == LOG_LEVELS.INFO:  
    logger.info(message)

  elif level == LOG_LEVELS.DEBUG:
    logger.debug(message)

  else:
    logger.log(logging.INFO, "Unknown Log Level: %s", level)

def close_log():
  logging.shutdown()
