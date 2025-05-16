import os
from rich.console import Console
import logging
from rich.logging import RichHandler
import sys
from datetime import datetime

# Configure rich logging
console = Console()

def setup_logging(level=logging.INFO):
    """Set up logging with rich formatting."""
    # Get the caller's frame
    frame = sys._getframe(1)
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s (%(filename)s:%(lineno)d)",
        datefmt="%H:%M:%S",
        force=True
    )
    
    # Add rich handler for better formatting
    rich_handler = RichHandler(
        show_time=False,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True
    )
    
    # Get the root logger and remove any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add our rich handler
    root_logger.addHandler(rich_handler)

def rich_log(level: str, message: str):
    """Log a message with rich formatting."""
    # Get the caller's frame
    frame = sys._getframe(1)
    
    # Create a logger with the caller's module name
    logger = logging.getLogger(frame.f_globals.get('__name__', 'root'))
    
    # Get the original source location
    filename = frame.f_code.co_filename
    lineno = frame.f_lineno
    
    # Log the message with the original source location
    log_func = getattr(logger, level.lower())
    log_func(f"{message} ({os.path.basename(filename)}:{lineno})")
    
    # Force flush the output
    console.file.flush()
    sys.stdout.flush()

def should_show_progress() -> bool:
    """Check if this process should show progress displays.
    Returns False if this is a child process or worker process."""
    return not os.environ.get('FICHERO_NO_PROGRESS', '').lower() in ('1', 'true', 'yes') 