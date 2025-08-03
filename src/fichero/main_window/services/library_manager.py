"""
Library Manager Service

Handles library directory setup, manifest creation, and library path management.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import asyncio
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class LibraryManager:
    """Service for managing the Fichero library"""
    
    def __init__(self, app):
        """Initialize library manager"""
        self.app = app
        self.settings = None
        try:
            from fichero.config.core.settings import get_app_settings
            self.settings = get_app_settings(app)
        except ImportError:
            logger.warning("Settings not available")
    
    def get_library_path(self) -> Path:
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
        return self.app.paths.data / "collections"
    
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
        """Initialize the library directory and create manifests for existing collections"""
        try:
            library_path = self.get_library_path()
            
            # Create library directory if it doesn't exist
            library_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Library directory: {library_path}")
            
            # Set the library path in settings if not already set
            if self.settings:
                try:
                    if not self.settings.get_setting("library.path", None):
                        self.set_library_path(library_path)
                except Exception as e:
                    logger.warning(f"Could not set library path in settings: {e}")
            
            # Create manifests for existing collections
            await self._create_manifests_for_existing_collections(library_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize library: {e}")
            return False
    
    async def _create_manifests_for_existing_collections(self, library_path: Path):
        """Create manifest files for existing collections in the projects directory"""
        try:
            # Look for existing collections in the projects directory
            projects_path = Path(__file__).parent.parent.parent.parent.parent / "projects"
            
            if not projects_path.exists():
                logger.info("No projects directory found")
                return
            
            # Find all subdirectories that contain image files
            collections_created = 0
            
            for project_dir in projects_path.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith('.'):
                    # Check if this directory contains image files
                    image_files = list(project_dir.glob("*.jpg")) + list(project_dir.glob("*.jpeg")) + list(project_dir.glob("*.png"))
                    
                    if image_files:
                        # Create manifest for this collection
                        manifest_path = library_path / f"{project_dir.name}.jsonl"
                        
                        if not manifest_path.exists():
                            await self._create_collection_manifest(manifest_path, project_dir, image_files)
                            collections_created += 1
                            logger.info(f"Created manifest for collection: {project_dir.name}")
            
            logger.info(f"Created {collections_created} collection manifests")
            
        except Exception as e:
            logger.error(f"Failed to create manifests for existing collections: {e}")
    
    async def _create_collection_manifest(self, manifest_path: Path, collection_dir: Path, image_files: List[Path]):
        """Create a manifest file for a collection"""
        try:
            # Sort image files naturally
            image_files.sort(key=lambda x: self._natural_sort_key(x.name))
            
            # Create manifest entries
            manifest_entries = []
            
            for i, image_file in enumerate(image_files):
                entry = {
                    "id": f"{collection_dir.name}_{i+1:03d}",
                    "filename": image_file.name,
                    "filepath": str(image_file),
                    "collection": collection_dir.name,
                    "index": i,
                    "total_files": len(image_files),
                    "timestamp": datetime.now().isoformat(),
                    "status": "pending",
                    "success": True,
                    "error": None,
                    "metadata": {
                        "file_size": image_file.stat().st_size,
                        "file_type": image_file.suffix.lower(),
                        "created": image_file.stat().st_ctime,
                        "modified": image_file.stat().st_mtime
                    }
                }
                manifest_entries.append(entry)
            
            # Write manifest file
            with open(manifest_path, 'w', encoding='utf-8') as f:
                for entry in manifest_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            logger.info(f"Created manifest with {len(manifest_entries)} entries: {manifest_path}")
            
        except Exception as e:
            logger.error(f"Failed to create manifest for {collection_dir.name}: {e}")
    
    def _natural_sort_key(self, s: str) -> List[Any]:
        """Natural sort key for sorting filenames with numbers"""
        import re
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split('([0-9]+)', s)]
    
    async def create_dummy_collections(self, count: int = 3) -> bool:
        """Create dummy collections for testing"""
        try:
            library_path = self.get_library_path()
            library_path.mkdir(parents=True, exist_ok=True)
            
            dummy_collections = [
                {
                    "name": "Historical Documents 2023",
                    "description": "Collection of historical documents from 2023",
                    "status": "Processed",
                    "entry_count": 45
                },
                {
                    "name": "Research Papers Q1",
                    "description": "Quarter 1 research paper collection",
                    "status": "In Progress", 
                    "entry_count": 23
                },
                {
                    "name": "Archive Photos",
                    "description": "Photographic archive collection",
                    "status": "Failed",
                    "entry_count": 12
                }
            ]
            
            for i, collection in enumerate(dummy_collections[:count]):
                manifest_path = library_path / f"{collection['name'].replace(' ', '_')}.jsonl"
                
                if not manifest_path.exists():
                    await self._create_dummy_manifest(manifest_path, collection)
                    logger.info(f"Created dummy collection: {collection['name']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create dummy collections: {e}")
            return False
    
    async def _create_dummy_manifest(self, manifest_path: Path, collection_info: Dict[str, Any]):
        """Create a dummy manifest file"""
        try:
            entries = []
            
            for i in range(collection_info['entry_count']):
                entry = {
                    "id": f"{collection_info['name'].replace(' ', '_')}_{i+1:03d}",
                    "filename": f"document_{i+1:03d}.jpg",
                    "filepath": f"/path/to/{collection_info['name'].replace(' ', '_')}/document_{i+1:03d}.jpg",
                    "collection": collection_info['name'],
                    "index": i,
                    "total_files": collection_info['entry_count'],
                    "timestamp": datetime.now().isoformat(),
                    "status": collection_info['status'].lower(),
                    "success": collection_info['status'] == 'Processed',
                    "error": None if collection_info['status'] == 'Processed' else "Sample error message",
                    "metadata": {
                        "file_size": 1024 * 1024,  # 1MB
                        "file_type": ".jpg",
                        "created": datetime.now().timestamp(),
                        "modified": datetime.now().timestamp()
                    }
                }
                entries.append(entry)
            
            # Write manifest file
            with open(manifest_path, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
        except Exception as e:
            logger.error(f"Failed to create dummy manifest: {e}") 