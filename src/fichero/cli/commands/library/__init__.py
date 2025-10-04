"""
Refactored Library Commands

Modular library command system with separated concerns.
"""

import typer
from rich.console import Console

from .base import BaseLibraryCommands
from .collection_commands import CollectionCommands
from .processing_commands import ProcessingCommands
from .import_export_commands import ImportExportCommands
from .item_commands import ItemCommands
from .stats_commands import StatsCommands
from .bulk_import_commands import BulkImportCommands
from .lookup_commands import LookupCommands
from .batch_commands import BatchCommands
from .cache_commands import CacheCommands


class LibraryCommands(BaseLibraryCommands):
    """Enhanced library commands with processing navigation"""
    
    def __init__(self, app_initializer):
        """Initialize enhanced library commands"""
        super().__init__(app_initializer)
        self.app = typer.Typer(name="library", help="Enhanced library management with processing navigation")
        
        # Initialize command modules
        self.collection_commands = CollectionCommands(app_initializer)
        self.processing_commands = ProcessingCommands(app_initializer)
        self.import_export_commands = ImportExportCommands(app_initializer)
        self.item_commands = ItemCommands(app_initializer)
        self.stats_commands = StatsCommands(app_initializer)
        self.bulk_import_commands = BulkImportCommands(app_initializer)
        self.lookup_commands = LookupCommands(app_initializer)
        self.batch_commands = BatchCommands(app_initializer)
        self.cache_commands = CacheCommands(app_initializer)
        
        # Register all commands
        self._register_commands()
    
    def _register_commands(self):
        """Register all enhanced library commands"""
        
        # Collection CRUD commands
        self.collection_commands.register_commands(self.app)
        
        # Processing navigation commands
        self.processing_commands.register_commands(self.app)
        
        # Import/export commands
        self.import_export_commands.register_commands(self.app)
        
        # Item management commands
        self.item_commands.register_commands(self.app)
        
        # Stats and utility commands
        self.stats_commands.register_commands(self.app)
        
        # Bulk import commands
        self.bulk_import_commands.register_commands(self.app)
        
        # Lookup commands
        self.lookup_commands.register_commands(self.app)
        
        # Batch operation commands
        self.batch_commands.register_commands(self.app)

        # Cache management commands
        self.cache_commands.register_commands(self.app)
