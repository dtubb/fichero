"""
Library Manager Service

Handles library directory setup, collection management, and flexible storage options.
Supports both local and external collections with configurable processing locations.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
import asyncio
import json
from datetime import datetime
import shutil

logger = logging.getLogger(__name__)


class CollectionInfo:
    """Represents a collection in the library"""
    
    def __init__(self, 
                 id: str,
                 name: str,
                 type: Literal["local", "external"],
                 location: str,
                 processing_location: Literal["internal", "external"] = "internal",
                 processing_path: Optional[str] = None,
                 description: str = "",
                 created: Optional[str] = None,
                 last_accessed: Optional[str] = None,
                 status: str = "available"):
        self.id = id
        self.name = name
        self.type = type
        self.location = location
        self.processing_location = processing_location
        self.processing_path = processing_path
        self.description = description
        self.created = created or datetime.now().isoformat()
        self.last_accessed = last_accessed or datetime.now().isoformat()
        self.status = status
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "processing_location": self.processing_location,
            "processing_path": self.processing_path,
            "description": self.description,
            "created": self.created,
            "last_accessed": self.last_accessed,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectionInfo':
        """Create from dictionary"""
        return cls(**data)
    
    def get_processing_output_path(self, app) -> Path:
        """Get the actual processing output path"""
        if self.processing_location == "internal":
            # Internal processing goes to app library
            library_path = Path(app.paths.data) / "library" / "processing"
            return library_path / self.name
        else:
            # External processing uses user-specified path
            return Path(self.processing_path) if self.processing_path else Path.home() / "Desktop" / "fichero_output"


class LibraryManager:
    """Service for managing the Fichero library with flexible storage options"""
    
    def __init__(self, app):
        """Initialize library manager"""
        self.app = app
        self.settings = None
        self.collections: List[CollectionInfo] = []
        self.library_path = self._get_library_path()
        self.manifest_path = self.library_path / "library.jsonl"
        
        try:
            from fichero.config.core.settings import get_app_settings
            self.settings = get_app_settings(app)
        except ImportError:
            logger.warning("Settings not available")
    
    def _get_library_path(self) -> Path:
        """Get the library path from settings or use default"""
        # Try to get from settings first
        if self.settings:
            try:
                library_path = self.settings.get_setting("library.path", None)
                if library_path:
                    return Path(library_path)
            except Exception as e:
                logger.warning(f"Could not get library path from settings: {e}")
        
        # Use Toga app paths as default
        return self.app.paths.data / "library"
    
    def set_library_path(self, path: Path) -> bool:
        """Set the library path in settings"""
        try:
            if self.settings:
                self.settings.set_setting("library.path", str(path))
                return True
        except Exception as e:
            logger.error(f"Failed to set library path: {e}")
        return False
    
    async def initialize_library(self) -> bool:
        """Initialize the library directory and load existing collections"""
        try:
            # Create library directory if it doesn't exist
            self.library_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Library directory: {self.library_path}")
            
            # Create subdirectories
            (self.library_path / "collections").mkdir(exist_ok=True)
            (self.library_path / "processing").mkdir(exist_ok=True)
            
            # Set the library path in settings if not already set
            if self.settings:
                try:
                    if not self.settings.get_setting("library.path", None):
                        self.set_library_path(self.library_path)
                except Exception as e:
                    logger.warning(f"Could not set library path in settings: {e}")
            
            # Load existing collections
            await self.load_collections()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize library: {e}")
            return False
    
    async def load_collections(self) -> bool:
        """Load collections from manifest file"""
        try:
            self.collections = []
            
            if not self.manifest_path.exists():
                logger.info("No library manifest found, starting with empty library")
                return True
            
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            collection = CollectionInfo.from_dict(data)
                            self.collections.append(collection)
                        except Exception as e:
                            logger.warning(f"Failed to parse collection line: {e}")
            
            logger.info(f"Loaded {len(self.collections)} collections from manifest")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load collections: {e}")
            return False
    
    async def save_collections(self) -> bool:
        """Save collections to manifest file"""
        try:
            # Create backup of existing manifest
            if self.manifest_path.exists():
                backup_path = self.manifest_path.with_suffix('.jsonl.backup')
                shutil.copy2(self.manifest_path, backup_path)
            
            # Write new manifest
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                for collection in self.collections:
                    f.write(json.dumps(collection.to_dict(), ensure_ascii=False) + '\n')
            
            logger.info(f"Saved {len(self.collections)} collections to manifest")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save collections: {e}")
            return False
    
    async def add_collection(self, 
                           name: str,
                           location: str,
                           collection_type: Literal["local", "external"],
                           processing_location: Literal["internal", "external"] = "internal",
                           processing_path: Optional[str] = None,
                           description: str = "") -> Optional[CollectionInfo]:
        """Add a new collection to the library"""
        try:
            # Validate location exists
            location_path = Path(location)
            if not location_path.exists():
                logger.error(f"Collection location does not exist: {location}")
                return None
            
            # Generate unique ID
            collection_id = f"collection_{len(self.collections) + 1:03d}"
            
            # If local collection, copy to library
            if collection_type == "local":
                library_collection_path = self.library_path / "collections" / name
                if library_collection_path.exists():
                    shutil.rmtree(library_collection_path)
                shutil.copytree(location_path, library_collection_path)
                location = str(library_collection_path)
                logger.info(f"Copied collection to library: {library_collection_path}")
            
            # Create collection info
            collection = CollectionInfo(
                id=collection_id,
                name=name,
                type=collection_type,
                location=location,
                processing_location=processing_location,
                processing_path=processing_path,
                description=description
            )
            
            # Add to collections list
            self.collections.append(collection)
            
            # Save to manifest
            await self.save_collections()
            
            logger.info(f"Added collection: {name} ({collection_type})")
            return collection
            
        except Exception as e:
            logger.error(f"Failed to add collection: {e}")
            return None
    
    async def remove_collection(self, collection_id: str) -> bool:
        """Remove a collection from the library"""
        try:
            # Find collection
            collection = next((c for c in self.collections if c.id == collection_id), None)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False
            
            # Remove local files if it's a local collection
            if collection.type == "local":
                collection_path = Path(collection.location)
                if collection_path.exists():
                    shutil.rmtree(collection_path)
                    logger.info(f"Removed local collection files: {collection_path}")
            
            # Remove from collections list
            self.collections = [c for c in self.collections if c.id != collection_id]
            
            # Save to manifest
            await self.save_collections()
            
            logger.info(f"Removed collection: {collection.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove collection: {e}")
            return False
    
    def get_collection(self, collection_id: str) -> Optional[CollectionInfo]:
        """Get a collection by ID"""
        return next((c for c in self.collections if c.id == collection_id), None)
    
    def get_collections(self) -> List[CollectionInfo]:
        """Get all collections"""
        return self.collections.copy()
    
    def update_collection_status(self, collection_id: str, status: str) -> bool:
        """Update collection status"""
        try:
            collection = self.get_collection(collection_id)
            if collection:
                collection.status = status
                collection.last_accessed = datetime.now().isoformat()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update collection status: {e}")
            return False
    
    async def scan_collection(self, collection_id: str) -> Dict[str, Any]:
        """Scan a collection and return metadata"""
        try:
            collection = self.get_collection(collection_id)
            if not collection:
                return {}
            
            location_path = Path(collection.location)
            if not location_path.exists():
                self.update_collection_status(collection_id, "unmounted")
                return {"error": "Collection location not accessible"}
            
            # Scan for files and folders
            image_files = list(location_path.glob("**/*.jpg")) + list(location_path.glob("**/*.jpeg")) + list(location_path.glob("**/*.png"))
            folders = [f for f in location_path.iterdir() if f.is_dir()]
            
            metadata = {
                "folder_count": len(folders),
                "image_count": len(image_files),
                "total_size": sum(f.stat().st_size for f in image_files if f.exists()),
                "last_scan": datetime.now().isoformat()
            }
            
            self.update_collection_status(collection_id, "available")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to scan collection: {e}")
            return {"error": str(e)}
    
    async def create_dummy_collections(self, count: int = 3) -> bool:
        """Create dummy collections for testing"""
        try:
            dummy_collections = [
                {
                    "name": "Historical Documents 2023",
                    "location": "/tmp/dummy_historical",
                    "type": "external",
                    "description": "Collection of historical documents from 2023"
                },
                {
                    "name": "Research Papers Q1", 
                    "location": "/tmp/dummy_research",
                    "type": "external",
                    "description": "Quarter 1 research paper collection"
                },
                {
                    "name": "Archive Photos",
                    "location": "/tmp/dummy_photos", 
                    "type": "external",
                    "description": "Photographic archive collection"
                }
            ]
            
            for i, collection_info in enumerate(dummy_collections[:count]):
                # Create dummy directory
                dummy_path = Path(collection_info["location"])
                dummy_path.mkdir(parents=True, exist_ok=True)
                
                # Add to library
                await self.add_collection(
                    name=collection_info["name"],
                    location=collection_info["location"],
                    collection_type=collection_info["type"],
                    description=collection_info["description"]
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create dummy collections: {e}")
            return False 