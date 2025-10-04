"""
Add Option Views Package

Individual views for each add option, following BaseView pattern.
Each view handles a specific type of content addition with proper navigation.
"""

from fichero.windows.add.views.file_view import FileAddView
from fichero.windows.add.views.folder_view import FolderAddView
from fichero.windows.add.views.url_view import URLAddView
from fichero.windows.add.views.website_view import WebsiteAddView
from fichero.windows.add.views.camera_view import CameraAddView
from fichero.windows.add.views.bulk_import_view import BulkImportView

__all__ = [
    "FileAddView",
    "FolderAddView",
    "URLAddView",
    "WebsiteAddView",
    "CameraAddView",
    "BulkImportView"
] 