"""
Data Models for Fichero Library System

Defines the core data structures for collections, items, and processing history.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field


@dataclass
class Collection:
    """Represents a collection of documents and resources"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: Literal["local", "external", "url", "hybrid"] = "local"
    source_path: Optional[str] = None
    local_path: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    sort_order: int = 0  # Manual sort order (0 = default/auto)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "source_path": self.source_path,
            "local_path": self.local_path,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "sort_order": self.sort_order,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Collection':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return cls(**data)


@dataclass
class CollectionItem:
    """Represents an individual item within a collection

    Metadata fields for Director integration:
        - director_task_id (str): Links to Director task
        - director_workflow (str): Workflow name used
        - director_output_path (str): Path to output folder
        - director_status (str): "pending" | "running" | "success" | "failed"
        - director_progress (float): 0-100
        - director_error (str): Error message if failed
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str = ""
    type: Literal["file", "folder", "url", "camera", "audio"] = "file"
    source_path: Optional[str] = None
    local_path: Optional[str] = None
    storage_type: Literal["external", "local", "url"] = "external"
    name: str = ""
    status: Literal["pending", "processing", "completed", "error"] = "pending"
    parent_id: Optional[str] = None  # For hierarchical folder structure
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "collection_id": self.collection_id,
            "type": self.type,
            "source_path": self.source_path,
            "local_path": self.local_path,
            "storage_type": self.storage_type,
            "name": self.name,
            "status": self.status,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectionItem':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return cls(**data)


@dataclass
class ProcessingResult:
    """Represents a processing operation result"""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    item_id: str = ""
    workflow: str = ""
    prompt_config: Optional[str] = None
    status: Literal["success", "failed", "partial"] = "success"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_paths: List[str] = field(default_factory=list)
    logs_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    llm_backend: Optional[str] = None
    processing_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "item_id": self.item_id,
            "workflow": self.workflow,
            "prompt_config": self.prompt_config,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output_paths": self.output_paths,
            "logs_path": self.logs_path,
            "metadata": self.metadata,
            "llm_backend": self.llm_backend,
            "processing_time": self.processing_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessingResult':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'started_at' in data and data['started_at']:
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if 'completed_at' in data and data['completed_at']:
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        
        return cls(**data)


@dataclass
class ProcessingOutput:
    """Tracks individual output files from processing steps

    Enables:
    - Finding outputs by type (transcriptions, word docs, etc.)
    - Tracking file-level vs batch-level outputs
    - Re-running steps when inputs change
    - Searching metadata extracted from outputs
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    processing_result_id: str = ""  # FK to ProcessingResult
    collection_id: str = ""  # For easier querying
    item_id: Optional[str] = None  # None for batch-level outputs
    step_name: str = ""  # e.g., "transcribe", "prepare_images", "catalogue_folder"
    source_file: Optional[str] = None  # Original file path (relative) for file-level outputs
    output_type: str = ""  # "transcription", "word_doc", "prepared_image", "json", "catalogue"
    output_path: str = ""  # Relative path from collection folder
    file_format: str = ""  # "txt", "docx", "jpg", "json", "md"
    file_size: Optional[int] = None  # In bytes
    file_modified: Optional[datetime] = None  # Last modified time (for detecting manual edits)
    created_at: datetime = field(default_factory=datetime.now)
    metadata_extracted: bool = False  # Whether metadata was extracted
    is_valid: bool = True  # False if inputs have changed (needs re-run)

    # For dependency tracking (re-running steps)
    depends_on_output_ids: List[str] = field(default_factory=list)  # Input outputs this step depends on

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "processing_result_id": self.processing_result_id,
            "collection_id": self.collection_id,
            "item_id": self.item_id,
            "step_name": self.step_name,
            "source_file": self.source_file,
            "output_type": self.output_type,
            "output_path": self.output_path,
            "file_format": self.file_format,
            "file_size": self.file_size,
            "file_modified": self.file_modified.isoformat() if self.file_modified else None,
            "created_at": self.created_at.isoformat(),
            "metadata_extracted": self.metadata_extracted,
            "is_valid": self.is_valid,
            "depends_on_output_ids": self.depends_on_output_ids
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessingOutput':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'file_modified' in data and data['file_modified']:
            data['file_modified'] = datetime.fromisoformat(data['file_modified'])

        return cls(**data)


@dataclass
class ExtractedMetadata:
    """Searchable metadata extracted from processing outputs

    Enables:
    - Full-text search across transcriptions
    - Finding mentions of entities (people, places, dates)
    - Searching catalogue data
    - Querying key quotes and summaries
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    processing_output_id: str = ""  # FK to ProcessingOutput
    collection_id: str = ""  # For easier querying
    item_id: Optional[str] = None  # For file-level metadata

    # Metadata type and content
    metadata_type: str = ""  # "transcription", "entity", "quote", "summary", "catalogue_field"
    key: str = ""  # Field name: "text", "person_name", "place", "date", "title", "description"
    value: str = ""  # The actual data

    # For AI-extracted data
    confidence: Optional[float] = None  # 0.0-1.0 for AI-extracted entities
    context: Optional[str] = None  # Surrounding text for quotes/entities

    # Indexing and search
    indexed: bool = False  # For full-text search indexing
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "processing_output_id": self.processing_output_id,
            "collection_id": self.collection_id,
            "item_id": self.item_id,
            "metadata_type": self.metadata_type,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "context": self.context,
            "indexed": self.indexed,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExtractedMetadata':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])

        return cls(**data)


@dataclass
class ExternalPath:
    """Represents an external path that needs monitoring"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str = ""
    path: str = ""
    last_seen: Optional[datetime] = None
    status: Literal["available", "unmounted", "error"] = "available"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "collection_id": self.collection_id,
            "path": self.path,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "status": self.status
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExternalPath':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'last_seen' in data and data['last_seen']:
            data['last_seen'] = datetime.fromisoformat(data['last_seen'])

        return cls(**data)


@dataclass
class ThumbnailRecord:
    """Represents a generated thumbnail with deduplication tracking"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_file_hash: str = ""  # SHA256 of source file content
    thumbnail_hash: str = ""  # SHA256 of thumbnail (for verification)
    thumbnail_path: str = ""  # Relative path from cache_dir: aa/bb/aabbcc...png
    size: str = ""  # e.g., "128x128"
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "source_file_hash": self.source_file_hash,
            "thumbnail_hash": self.thumbnail_hash,
            "thumbnail_path": self.thumbnail_path,
            "size": self.size,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThumbnailRecord':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'last_accessed' in data and isinstance(data['last_accessed'], str):
            data['last_accessed'] = datetime.fromisoformat(data['last_accessed'])

        return cls(**data) 