#src/common/__init__.py

from .sb_custom_errors import *
from .sb_constants import *
from .sb_verbose import verbose_print, configure_verbosity
from .sb_log import log, configure_log_level, logger, close_log
from .sb_debug import is_debugging, configure_debug_level
from .sb_utils import log_and_print

__all__ = [
  "verbose_print",
  "configure_verbosity",
  "log",

  "configure_log_level",

  "is_debugging", 
  "configure_debug_level",

  "close_log",
  
  "log_and_print",
  
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
    
  "DEFAULT_LAB_FOLDER_NAME",
  "LAB_LOG_FILE_NAME",
  "LAB_LOG_FILE_EXTENSION",
  "LAB_CONVERSATION_ID_FORMAT",
  "LAB_CONVERSATION_DATA_FIELDS",
  
  "DEFAULT_SLIPS_FOLDER_NAME",
  "DEFAULT_TAGS_FOLDER_NAME",
  "DEFAULT_REFERENCES_FOLDER_NAME",
  "DEFAULT_EXTRACTED_METADATA_FOLDER_NAME",

  "DEFAULT_LOG_FILE_NAME",

  "DEFAULT_SLIP_FORMAT",
  "DEFAULT_TAG_FORMAT",
  "DEFAULT_REFERENCE_FORMAT",
  
  "source_md_file_validation_error",
  
  "DEFAULT_LLM",
  "DEFAULT_LLM_MODEL"
]