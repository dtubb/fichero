"""
Import/Export functionality for Fichero Collections

Handles collection packaging and unpacking using ZIP + JSONL format.
"""

import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import uuid

try:
    from fichero.library.models import Collection, CollectionItem, ProcessingResult
    from fichero.library.storage import LibraryStorage
except ImportError:
    try:
        from .models import Collection, CollectionItem, ProcessingResult
        from .storage import LibraryStorage
    except ImportError:
        # Direct import for testing
        import models
        import storage
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        LibraryStorage = storage.LibraryStorage

logger = logging.getLogger(__name__)


class CollectionExporter:
    """Exports collections to portable ZIP + JSONL format"""
    
    def __init__(self, storage: LibraryStorage):
        """Initialize exporter with storage backend"""
        self.storage = storage
    
    def export_collection(self, collection_id: str, output_path: Path, include_files: bool = False) -> bool:
        """Export a collection to ZIP + JSONL format"""
        try:
            # Get collection data
            collection = self.storage.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False
            
            # Get collection items
            items = self.storage.get_collection_items(collection_id)
            
            # Get processing history for all items
            processing_history = []
            for item in items:
                history = self.storage.get_processing_history(item.id)
                processing_history.extend(history)
            
            # Create export data structure
            export_data = {
                "collection": collection.to_dict(),
                "items": [item.to_dict() for item in items],
                "processing_history": [result.to_dict() for result in processing_history],
                "exported_at": datetime.now().isoformat(),
                "export_version": "1.0"
            }
            
            # Create ZIP file
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add metadata as JSONL
                metadata_content = self._create_jsonl_content(export_data)
                zip_file.writestr("collection.jsonl", metadata_content)
                
                # Add files if requested
                if include_files:
                    self._add_files_to_zip(zip_file, collection, items)
            
            logger.info(f"Collection exported successfully: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export collection: {e}")
            return False
    
    def _create_jsonl_content(self, export_data: Dict[str, Any]) -> str:
        """Create JSONL content from export data"""
        lines = []
        
        # Collection info
        lines.append(json.dumps({"type": "collection", **export_data["collection"]}, ensure_ascii=False))
        
        # Items
        for item in export_data["items"]:
            lines.append(json.dumps({"type": "item", **item}, ensure_ascii=False))
        
        # Processing history
        for result in export_data["processing_history"]:
            lines.append(json.dumps({"type": "processing", **result}, ensure_ascii=False))
        
        # Export metadata
        lines.append(json.dumps({"type": "export_metadata", **{k: v for k, v in export_data.items() if k not in ["collection", "items", "processing_history"]}}, ensure_ascii=False))
        
        return "\n".join(lines)
    
    def _add_files_to_zip(self, zip_file: zipfile.ZipFile, collection: Collection, items: List[CollectionItem]):
        """Add collection files to ZIP archive"""
        try:
            # Add local files if they exist
            for item in items:
                if item.local_path and Path(item.local_path).exists():
                    file_path = Path(item.local_path)
                    if file_path.is_file():
                        # Add file to ZIP with relative path
                        zip_file.write(file_path, f"files/{item.name}")
                    elif file_path.is_dir():
                        # Add directory contents
                        for sub_file in file_path.rglob("*"):
                            if sub_file.is_file():
                                relative_path = sub_file.relative_to(file_path)
                                zip_file.write(sub_file, f"files/{item.name}/{relative_path}")
            
            logger.debug("Files added to export ZIP")
            
        except Exception as e:
            logger.warning(f"Failed to add files to ZIP: {e}")


class CollectionImporter:
    """Imports collections from ZIP + JSONL format"""
    
    def __init__(self, storage: LibraryStorage):
        """Initialize importer with storage backend"""
        self.storage = storage
    
    async def import_collection(self, import_path: Path, target_collection_name: Optional[str] = None) -> Optional[str]:
        """Import a collection from ZIP + JSONL format"""
        try:
            if not import_path.exists():
                logger.error(f"Import file not found: {import_path}")
                return None
            
            # Extract and parse metadata
            with zipfile.ZipFile(import_path, 'r') as zip_file:
                # Read collection metadata
                if "collection.jsonl" not in zip_file.namelist():
                    logger.error("No collection.jsonl found in import file")
                    return None
                
                metadata_content = zip_file.read("collection.jsonl").decode('utf-8')
                import_data = self._parse_jsonl_content(metadata_content)
                
                if not import_data:
                    logger.error("Failed to parse import metadata")
                    return None
            
            # Import collection
            collection_id = await self._import_collection_data(import_data, target_collection_name)
            
            # Extract files if present
            if collection_id:
                self._extract_imported_files(import_path, import_data, collection_id)
            
            logger.info(f"Collection imported successfully: {collection_id}")
            return collection_id
            
        except Exception as e:
            logger.error(f"Failed to import collection: {e}")
            return None
    
    def _parse_jsonl_content(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSONL content into structured data"""
        try:
            collection_data = None
            items_data = []
            processing_data = []
            export_metadata = None
            
            for line in content.strip().split('\n'):
                if not line.strip():
                    continue
                
                try:
                    data = json.loads(line)
                    data_type = data.get('type')
                    
                    if data_type == 'collection':
                        collection_data = data
                    elif data_type == 'item':
                        items_data.append(data)
                    elif data_type == 'processing':
                        processing_data.append(data)
                    elif data_type == 'export_metadata':
                        export_metadata = data
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSONL line: {e}")
                    continue
            
            if not collection_data:
                return None
            
            return {
                "collection": collection_data,
                "items": items_data,
                "processing_history": processing_data,
                "export_metadata": export_metadata
            }
            
        except Exception as e:
            logger.error(f"Failed to parse JSONL content: {e}")
            return None
    
    async def _import_collection_data(self, import_data: Dict[str, Any], target_name: Optional[str] = None) -> Optional[str]:
        """Import collection data into storage"""
        try:
            # Prepare collection data
            collection_dict = import_data["collection"]
            if target_name:
                collection_dict["name"] = target_name
            
            # Generate new ID for imported collection
            collection_dict["id"] = str(uuid.uuid4())
            collection_dict["created_at"] = datetime.now().isoformat()
            collection_dict["updated_at"] = datetime.now().isoformat()
            
            # Create collection
            collection = Collection.from_dict(collection_dict)
            if not self.storage.add_collection(collection):
                logger.error("Failed to add imported collection to storage")
                return None
            
            # Import items
            for item_dict in import_data["items"]:
                item_dict["id"] = str(uuid.uuid4())
                item_dict["collection_id"] = collection.id
                item_dict["created_at"] = datetime.now().isoformat()
                item_dict["updated_at"] = datetime.now().isoformat()
                
                item = CollectionItem.from_dict(item_dict)
                if not self.storage.add_collection_item(item):
                    logger.warning(f"Failed to import item: {item.name}")
            
            # Import processing history
            for result_dict in import_data["processing_history"]:
                # Find corresponding item by name
                item_name = result_dict.get("item_name", "")
                matching_items = [item for item in import_data["items"] if item.get("name") == item_name]
                
                if matching_items:
                    result_dict["id"] = str(uuid.uuid4())
                    result_dict["item_id"] = matching_items[0]["id"]
                    result_dict["started_at"] = datetime.now().isoformat()
                    result_dict["completed_at"] = datetime.now().isoformat()
                    
                    result = ProcessingResult.from_dict(result_dict)
                    if not self.storage.add_processing_result(result):
                        logger.warning(f"Failed to import processing result: {result.workflow}")
            
            return collection.id
            
        except Exception as e:
            logger.error(f"Failed to import collection data: {e}")
            return None
    
    def _extract_imported_files(self, import_path: Path, import_data: Dict[str, Any], collection_id: str):
        """Extract imported files to appropriate locations"""
        try:
            collection = self.storage.get_collection(collection_id)
            if not collection:
                return
            
            # Create local collection directory if needed
            if collection.type == "local":
                local_path = Path(collection.local_path) if collection.local_path else None
                if local_path:
                    local_path.mkdir(parents=True, exist_ok=True)
                    
                    # Extract files from ZIP
                    with zipfile.ZipFile(import_path, 'r') as zip_file:
                        for file_info in zip_file.filelist:
                            if file_info.filename.startswith("files/"):
                                zip_file.extract(file_info, local_path.parent)
                    
                    logger.debug(f"Imported files extracted to: {local_path}")
            
        except Exception as e:
            logger.warning(f"Failed to extract imported files: {e}")


# Convenience function for quick export
def export_collection_to_file(storage: LibraryStorage, collection_id: str, output_path: Path, include_files: bool = False) -> bool:
    """Quick export function"""
    exporter = CollectionExporter(storage)
    return exporter.export_collection(collection_id, output_path, include_files)


# Convenience function for quick import
async def import_collection_from_file(storage: LibraryStorage, import_path: Path, target_name: Optional[str] = None) -> Optional[str]:
    """Quick import function"""
    importer = CollectionImporter(storage)
    return await importer.import_collection(import_path, target_name) 