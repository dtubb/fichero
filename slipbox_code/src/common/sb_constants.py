#src/common/sb_constants.py

from enum import Enum, auto

import os
import pathlib

class VerbosityLevel(Enum):
  NONE = auto()
  INFO = auto()
  ERROR = auto()
  WARNING = auto()
  DETAILED = auto()
  DEBUG = auto()

class LogLevel(Enum):
  NONE = auto()
  FATAL = auto()
  CRITICAL = auto()
  ERROR = auto()
  WARNING = auto()
  INFO = auto()
  DEBUG = auto() 

class DebugLevel(Enum):
  INACTIVE = auto()
  ACTIVE = auto()

VERBOSITY_LEVELS = VerbosityLevel   
LOG_LEVELS = LogLevel
DEBUG_LEVELS = DebugLevel

# File extensions
ALLOWED_EXTENSIONS = [".pdf", ".txt", ".md",".jpg"] 

# Get home folder path 
HOME_DIR = pathlib.Path.home()

# Set default slipbox folder under home dir
DEFAULT_SLIPBOX_FOLDER_NAME = "slipbox"
DEFAULT_SLIPBOX_PATH = os.path.join(HOME_DIR, DEFAULT_SLIPBOX_FOLDER_NAME) 

# File and folder names
DEFAULT_INBOX_FOLDER_NAME = "inbox"

DEFAULT_SOURCES_FOLDER_NAME = "sources"  
DEFAULT_SOURCES_FILE_EXTENSION = "-source.md"
DEFAULT_ORIGINAL_FILE_SUFFIX = "-original"
DEFAULT_EXTRACTS_FILE_SUFFIX = "-extracts.md"
DEFAULT_EXTRACTS_OCR_CLEANED_FILE_SUFFIX = "-extracts-ocr-cleaned.md"
DEFAULT_CATALOGUE_FILE_SUFFIX = "-catalogue.md"
DEFAULT_EXTRACTED_METADATA_FILE_SUFFIX = "-metadata.md"

DEFAULT_SLIPS_FOLDER_NAME = "slips"
DEFAULT_TAGS_FOLDER_NAME = "tags"
DEFAULT_REFERENCES_FOLDER_NAME = "references"
DEFAULT_EXTRACTED_METADATA_FOLDER_NAME = "metadata"

DEFAULT_LAB_FOLDER_NAME = "labs"
LAB_LOG_FILE_NAME = "lab-log"
LAB_LOG_FILE_EXTENSION = ".txt"
LAB_CONVERSATION_ID_FORMAT = "convo-{timestamp}"
LAB_CONVERSATION_DATA_FIELDS = ["id","agent","prompt","response"]

# File names
DEFAULT_LOG_FILE_NAME = "log.txt"

# Data file formats
DEFAULT_SLIP_FORMAT = "md" # markdown 
DEFAULT_TAG_FORMAT = "md"
DEFAULT_REFERENCE_FORMAT = "bib" # bibtex

# SlipBox Numbering format:

# Set default input folder under default slipbox folder
DEFAULT_INPUT_PATH = os.path.join(DEFAULT_SLIPBOX_PATH, "inbox/*")

#DEFAULT_LLM = "ollama"
DEFAULT_LLM = "openai"

# Set default input folder under default slipbox folder
#DEFAULT_LLM_MODEL = "gpt-3.5-turbo-0613"
#DEFAULT_LLM_MODEL = "gpt-4-1106-preview"
DEFAULT_LLM_MODEL = "gpt-4"

__all__ = [
  "VERBOSITY_LEVELS",
  "LOG_LEVELS", 
  "DEBUG_LEVELS",
  "ALLOWED_EXTENSIONS",
  
  "DEFAULT_INPUT_PATH",

  "DEFAULT_SLIPBOX_PATH",
  "DEFAULT_SLIPBOX_FOLDER_NAME",
  
  "DEFAULT_INBOX_FOLDER_NAME",

  "DEFAULT_SOURCES_FOLDER_NAME",
  "DEFAULT_SOURCES_FILE_EXTENSION",
  "DEFAULT_ORIGINAL_FILE_SUFFIX",
  "DEFAULT_EXTRACTS_FILE_SUFFIX",
	"DEFAULT_EXTRACTS_OCR_CLEANED_FILE_SUFFIX",
  "DEFAULT_CATALOGUE_FILE_SUFFIX",
  "DEFAULT_EXTRACTED_METADATA_FILE_SUFFIX",
  
  "DEFAULT_SLIPS_FOLDER_NAME",
  "DEFAULT_TAGS_FOLDER_NAME",
  "DEFAULT_REFERENCES_FOLDER_NAME",
  "DEFAULT_EXTRACTED_METADATA_FOLDER_NAME",
  
  "DEFAULT_LAB_FOLDER_NAME",
  "LAB_LOG_FILE_NAME",
  "LAB_LOG_FILE_EXTENSION",
  "LAB_CONVERSATION_ID_FORMAT",
  "LAB_CONVERSATION_DATA_FIELDS",

  "DEFAULT_LOG_FILE_NAME",

  "DEFAULT_SLIP_FORMAT",
  "DEFAULT_TAG_FORMAT",
  "DEFAULT_REFERENCE_FORMAT",
  
  "DEFAULT_LLM",
  "DEFAULT_LLM_MODEL"
]
