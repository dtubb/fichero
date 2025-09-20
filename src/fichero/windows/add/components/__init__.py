"""
Add Dialog Components

UI components for different types of content selection.
All components implement execute() method for new architecture.
"""

from fichero.windows.add.components.file_selector import FileSelector
from fichero.windows.add.components.folder_selector import FolderSelector
from fichero.windows.add.components.url_selector import URLSelector
from fichero.windows.add.components.website_selector import WebsiteSelector
from fichero.windows.add.components.camera_selector import CameraSelector
from fichero.windows.add.components.transcription_selector import TranscriptionSelector

__all__ = [
    "FileSelector",
    "FolderSelector", 
    "URLSelector",
    "WebsiteSelector",
    "CameraSelector",
    "TranscriptionSelector"
]
