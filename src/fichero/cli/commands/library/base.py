"""
Base Library Commands

Common functionality shared across library command modules.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from unittest.mock import Mock
from rich.console import Console

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage
from fichero.library.processing_navigator import ProcessingNavigator
from fichero.library.director_bridge import LibraryDirectorBridge
from fichero.director.director_service import FicheroDirector


class BaseLibraryCommands:
    """Base class for library command functionality"""
    
    def __init__(self, app_initializer=None):
        """Initialize base library commands"""
        self.app_initializer = app_initializer
        self.console = Console()
        
        # Create mock app for settings access
        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"
        mock_app.paths.config = Path.home() / "Library" / "Preferences" / "ca.tubb.fichero"
        
        # Use centralized library path resolver (same as GUI and tests)
        from fichero.library.path_resolver import get_library_database_path
        db_path = get_library_database_path(mock_app)
        
        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        storage = LibraryStorage(db_path)
        
        # Create a mock app object for the library manager
        mock_app_for_manager = Mock()
        mock_app_for_manager.paths = Mock()
        mock_app_for_manager.paths.data = db_path.parent.parent  # Parent of library dir

        # Initialize library manager first
        self.library_manager = LibraryManager(mock_app_for_manager)

        # Initialize director and its backend
        self.director = FicheroDirector()
        # CRITICAL: Initialize backend to create task_manager and processing_coordinator
        if not self.director.initialize_backend():
            self.console.print("[red]Failed to initialize Fichero Director backend[/red]")

        self.bridge = LibraryDirectorBridge(self.director)

        # Initialize director integration service
        from fichero.library.director_integration import DirectorIntegrationService
        mock_app_for_manager.director_integration = DirectorIntegrationService(
            app=mock_app_for_manager,
            library_manager=self.library_manager,
            director=self.director
        )
    
    async def get_collection_by_id(self, collection_id: str):
        """Get collection by ID"""
        try:
            collections = await self.library_manager.get_all_collections()
            
            for collection in collections:
                if str(collection.id) == collection_id:
                    return collection
            
            self.console.print(f"[red]Collection with ID '{collection_id}' not found[/red]")
            return None
            
        except Exception as e:
            self.console.print(f"[red]Failed to get collection: {e}[/red]")
            return None
    
    def get_navigator_for_collection(self, collection):
        """Get ProcessingNavigator for a collection"""
        collection_path = Path(collection.local_path) if collection.local_path else None
        if not collection_path or not collection_path.exists():
            self.console.print(f"[red]Collection path not found: {collection_path}[/red]")
            return None
        
        return ProcessingNavigator(collection_path)
