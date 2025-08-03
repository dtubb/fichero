"""
Collection Scanner Service

Scans for and discovers collections in the project library directory.
Provides collection metadata including document counts, sizes, and processing status.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass

# Conditional imports for iOS compatibility
try:
    import srsly
    SRSLY_AVAILABLE = True
except ImportError:
    SRSLY_AVAILABLE = False
    # Create fallback functions for srsly functionality
    class srsly:
        @staticmethod
        def read_jsonl(path):
            import json
            data = []
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
            return data

from fichero.main_window.data.collection_data import CollectionData

logger = logging.getLogger(__name__)


class CollectionScanner:
    """Service for scanning and extracting collection information"""
    
    def __init__(self):
        """Initialize collection scanner"""
        pass
    
    async def scan_collections(self, library_path: Path) -> List[CollectionData]:
        """Scan for collection manifests and extract information"""
        collections = []
        
        if not library_path.exists():
            logger.warning(f"Library path does not exist: {library_path}")
            return collections
        
        # Look for manifest files
        for manifest_file in library_path.rglob("*.jsonl"):
            try:
                # Extract collection info from manifest
                collection_info = await self._extract_collection_info(manifest_file)
                if collection_info:
                    collections.append(collection_info)
            except Exception as e:
                logger.warning(f"Failed to process manifest {manifest_file}: {e}")
        
        # Sort by modification time (newest first)
        collections.sort(key=lambda x: x.modified, reverse=True)
        
        return collections
    
    async def _extract_collection_info(self, manifest_path: Path) -> Optional[CollectionData]:
        """Extract collection information from manifest file"""
        try:
            # Read the first few entries to get collection info
            
            if not manifest_path.exists():
                return None
            
            # Get basic file info
            stat = manifest_path.stat()
            parent_dir = manifest_path.parent.name
            
            # Try to read first entry for more info
            first_entry = None
            if SRSLY_AVAILABLE:
                try:
                    for entry in srsly.read_jsonl(manifest_path):
                        first_entry = entry
                        break
                except Exception:
                    pass
            
            # Build collection info
            collection_info = {
                'id': str(manifest_path),
                'title': parent_dir,
                'subtitle': f"Modified: {stat.st_mtime}",
                'manifest_path': manifest_path,
                'parent_dir': parent_dir,
                'modified': stat.st_mtime,
                'size': stat.st_size,
                'entry_count': 0,
                'status': 'Unknown'
            }
            
            # Count entries
            if SRSLY_AVAILABLE:
                try:
                    collection_info['entry_count'] = sum(1 for _ in srsly.read_jsonl(manifest_path))
                except Exception:
                    pass
            
            # Determine status based on content
            if first_entry:
                if 'success' in first_entry:
                    collection_info['status'] = 'Processed' if first_entry['success'] else 'Failed'
                elif 'error' in first_entry:
                    collection_info['status'] = 'Failed'
                else:
                    collection_info['status'] = 'In Progress'
            
            return CollectionData.from_manifest(manifest_path, collection_info)
            
        except Exception as e:
            logger.warning(f"Failed to extract collection info from {manifest_path}: {e}")
            return None 