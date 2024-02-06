# src/sb_utils/sb_img_to_text.py

import os
from pathlib import Path  

# Import from google, google vision
from google.cloud import vision
import google.auth.transport.requests
from google.auth.transport.requests import Request
from google.cloud import vision

# Import SlipBox’s common functions and constants.
from src.common import *

# type_ =  'DOCUMENT_TEXT_DETECTION' #@param ['TEXT_DETECTION', "DOCUMENT_TEXT_DETECTION", "LABEL_DETECTION", "IMAGE_PROPERTIES", "OBJECT_LOCALIZATION", "WEB_DETECTION" ] {type:"string"}

# APIKEY= os.getenv("VISION_API_KEY")  # Replace with your API key

access_token_path = "/Users/dtubb/slipbox_code/slipbox/credentials/access_token-google-vision.txt"

# Function to extract text from PDF
def sb_img_to_text(input_img, output_path):

  # Check if input is a JPG file
  if Path(input_img).suffix == '.jpg':
    img_path = Path(input_img) 
  else:
    raise ValueError("Invalid JPG input")

  # Check if output is a directory
  if os.path.isdir(output_path):
    
    # If directory, use PDF filename as output file
    filename = img_path.stem + '.txt'
    output_file = os.path.join(output_path, filename)

  else:
    # If not a directory, treat as file path 
    output_file = output_path
  
  # Initialize Google Vision with google credientials.
  log_and_print(f"Loading client.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
  try:
    with open(access_token_path) as f:
      api_key = f.read()
         
    # client = vision.ImageAnnotatorClient(credentials=api_key)
    client = vision.ImageAnnotatorClient()

    log_and_print(f"Succcess in creating client.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO) 
    
  except Exception as e:
    log_and_print(f"Error creating client: {e}", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO) 

  # Open image and get content
  log_and_print(f"Loading JPG.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
  
  try:
    with open(input_img, "rb") as image_file:
      content = image_file.read()  

    log_and_print(f"File loaded.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    
    image = vision.Image(content=content)
    
    log_and_print(f"Image created.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

    # text_detection_response = client.text_detection(image=image)
      
  except Exception as e:
    log_and_print(f"JPG not loaded: {e}", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
  
    response = client.document_text_detection(image=image)

  # Send image and google visions
  try:

    log_and_print(f"Image sent to Google Vision.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  except Exception as e:
      log_and_print(f"Error {e}.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  # Call Vision API
  log_and_print(f"Sending to google.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  try:
    response = client.text_detection(image=image)
    # log_and_print(f"Google response: {response}", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    text = response.full_text_annotation.text

  except Exception as e:
    log_and_print(f"Error in document detection via Google vision client: {e}.", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  # log_and_print(f"Google Vision extracted the text: {text}", LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  # Open output text file for writing 
  try:
    with open(output_file, 'w') as f:
     # Write concatenated text from all pages to output file
      f.write(text)

    # Log that extraction completed successfully 
    log_and_print(f'Text extracted to {output_file}', LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)

  # Catch any errors and log
  except:
    log_and_print('Error writing text file', LOG_LEVELS.INFO, VERBOSITY_LEVELS.INFO)
    raise