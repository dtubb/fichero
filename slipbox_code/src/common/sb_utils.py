#src/common/sb_utils.py 

# Import SlipBox’s common functions and constants.
from src.common import *

def log_and_print(msg, log_level, verbosity_level):
  log(msg, log_level)
  verbose_print(msg, verbosity_level)