# src/utils/sb_langchain_json_to_dictionary.py.py

# Import SlipBox’s common functions and constants.
from src.common import *

import json

def sb_langchain_json_to_dictionary(json_string):

  print("sb_langchain_json_to_dictionary")
 
  # Remove backticks
  no_backticks = json_string.replace("`", "")
  no_backticks = no_backticks.replace("json\n", "")


  print(f"""JSON result:
==============
{no_backticks}
==============""")
  # Load JSON 
  
  print(no_backticks)
  data = json.loads(no_backticks)
  
  # Log parsed data
  for key, value in data.items():
    print(f"{key}: {value}")

  # Return dictionary directly
  return data