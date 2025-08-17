"""
Document Scanner Service

Scans for and discovers documents within collections.
Provides document metadata including processing status, file sizes, and counts.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
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

from fichero.windows.main.data.document_data import DocumentData

logger = logging.getLogger(__name__)


class DocumentScanner:
    """Service for scanning and extracting document information"""
    
    def __init__(self):
        """Initialize document scanner"""
        pass
    
    async def scan_documents(self, library_path: Path) -> List[DocumentData]:
        """Scan for document manifests and extract information"""
        documents = []
        
        if not library_path.exists():
            logger.warning(f"Library path does not exist: {library_path}")
            return documents
        
        # Look for manifest files
        for manifest_file in library_path.rglob("*.jsonl"):
            try:
                # Extract document info from manifest
                doc_info = await self._extract_document_info(manifest_file)
                if doc_info:
                    documents.append(doc_info)
            except Exception as e:
                logger.warning(f"Failed to process manifest {manifest_file}: {e}")
        
        # Sort by modification time (newest first)
        documents.sort(key=lambda x: x.modified, reverse=True)
        
        return documents
    
    async def _extract_document_info(self, manifest_path: Path) -> Optional[DocumentData]:
        """Extract document information from manifest file"""
        try:
            # Read the first few entries to get document info
            
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
            
            # Build document info
            doc_info = {
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
                    doc_info['entry_count'] = sum(1 for _ in srsly.read_jsonl(manifest_path))
                except Exception:
                    pass
            
            # Determine status based on content
            if first_entry:
                if 'success' in first_entry:
                    doc_info['status'] = 'Processed' if first_entry['success'] else 'Failed'
                elif 'error' in first_entry:
                    doc_info['status'] = 'Failed'
                else:
                    doc_info['status'] = 'In Progress'
            
            return DocumentData.from_manifest(manifest_path, doc_info)
            
        except Exception as e:
            logger.warning(f"Failed to extract document info from {manifest_path}: {e}")
            return None 