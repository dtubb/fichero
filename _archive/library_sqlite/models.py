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

    Note: Director processing data is now tracked in the ProcessingResult table,
    NOT in the metadata dict. The item.status field reflects processing state:
        - "pending": Not yet processed
        - "processing": Currently being processed
        - "completed": Successfully processed
        - "error": Processing failed or was cancelled

    Use ProcessingResult table for detailed workflow information (workflow name,
    output paths, step status, etc.)
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

    def __post_init__(self):
        """Validate storage_type value after initialization"""
        valid_storage_types = ("external", "local", "url")
        if self.storage_type not in valid_storage_types:
            raise ValueError(
                f"Invalid storage_type: {self.storage_type}. "
                f"Must be one of: {valid_storage_types}"
            )

        # Validate storage_type consistency with paths
        if self.storage_type == "url" and self.source_path:
            # URL items should have http/https source_path
            if isinstance(self.source_path, str) and not self.source_path.startswith(('http://', 'https://')):
                # Warning only - don't fail, as this might be legacy data
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Item {self.id}: storage_type='url' but source_path doesn't start with http:// or https://: {self.source_path[:50] if self.source_path else 'None'}"
                )

        elif self.storage_type == "local" and not self.local_path:
            # Local items must have local_path
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Item {self.id}: storage_type='local' but local_path is not set"
            )

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

    # Model/provider tracking (populated from workflow_manifest.json model_info)
    model_name: Optional[str] = None  # e.g., "qwen-vl-ocr", "gpt-4o", "claude-3-opus"
    provider_name: Optional[str] = None  # e.g., "dashscope", "openai", "anthropic", "lmstudio"
    model_version: Optional[str] = None  # Model version if available
    api_endpoint: Optional[str] = None  # API endpoint URL
    api_parameters: Optional[str] = None  # JSON string of API params (temperature, max_tokens, etc.)
    usage_stats: Optional[str] = None  # JSON string with token usage, cost, etc.

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
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "model_version": self.model_version,
            "api_endpoint": self.api_endpoint,
            "api_parameters": self.api_parameters,
            "usage_stats": self.usage_stats,
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
    """Searchable metadata extracted from processing outputs with versioning support

    Enables:
    - Full-text search across transcriptions
    - Finding mentions of entities (people, places, dates)
    - Searching catalogue data
    - Querying key quotes and summaries
    - Multiple labeled versions (e.g., ai_qwen_v1, human_corrected_v2)
    - Custom fields for extensibility
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    processing_output_id: str = ""  # FK to ProcessingOutput
    collection_id: str = ""  # For easier querying
    item_id: Optional[str] = None  # For file-level metadata (None for collection-level)
    collection_level: bool = False  # True for collection-level metadata, False for file-level

    # Metadata schema and versioning
    schema_type: str = ""  # Schema: "transcription", "translation", "catalogue", "named_entities", etc.
    source_label: str = ""  # Source: "ai_qwen", "human_corrected", "google_translate", etc.
    version: int = 1  # Version number for this source_label
    schema_version: int = 1  # Schema version for evolution/migration

    # Metadata content
    key: str = ""  # Field name: "text", "language", "title", "entity_text", etc.
    value: str = ""  # The actual data

    # For AI-extracted data
    confidence: Optional[float] = None  # 0.0-1.0 for AI-extracted entities
    context: Optional[str] = None  # Surrounding text for quotes/entities

    # Model/provider tracking for version comparison
    model_name: Optional[str] = None  # e.g., "qwen-vl-ocr", "gpt-4o", "claude-3-opus"
    provider_name: Optional[str] = None  # e.g., "dashscope", "openai", "anthropic"
    edited_by: Optional[str] = None  # "user", "ai", or specific username for user edits

    # Extensibility
    custom_fields: Dict[str, Any] = field(default_factory=dict)  # Arbitrary additional fields

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
            "collection_level": self.collection_level,
            "schema_type": self.schema_type,
            "source_label": self.source_label,
            "version": self.version,
            "schema_version": self.schema_version,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "context": self.context,
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "edited_by": self.edited_by,
            "custom_fields": self.custom_fields,
            "indexed": self.indexed,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExtractedMetadata':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])

        # Handle backward compatibility with old 'metadata_type' field
        if 'metadata_type' in data and 'schema_type' not in data:
            data['schema_type'] = data.pop('metadata_type')

        # Provide defaults for new fields if missing (backward compatibility)
        data.setdefault('source_label', 'unknown')
        data.setdefault('version', 1)
        data.setdefault('schema_version', 1)
        data.setdefault('custom_fields', {})
        data.setdefault('collection_level', False)
        data.setdefault('model_name', None)
        data.setdefault('provider_name', None)
        data.setdefault('edited_by', None)

        return cls(**data)


@dataclass
class StepFile:
    """Tracks individual files stored in the library for processing steps

    Enables:
    - Store step output files directly in library (no need for external Director output folders)
    - Version multiple file outputs per step per item
    - Track file metadata and relationships
    - Support binary files (images, PDFs, etc.) and text files
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    item_id: str = ""  # FK to CollectionItem
    collection_id: str = ""  # For easier querying
    step_name: str = ""  # e.g., "prepare_images", "transcribe", "crop"
    source_label: str = ""  # e.g., "ai_qwen", "manual_edit", "yolo_v8"
    version: int = 1  # Version number for this step+source_label combination

    # File information
    file_name: str = ""  # Original filename (e.g., "document_001.jpg")
    file_path: str = ""  # Relative path from library storage root
    file_format: str = ""  # "jpg", "json", "txt", "docx"
    file_size: Optional[int] = None  # In bytes
    file_hash: Optional[str] = None  # SHA256 for deduplication
    mime_type: Optional[str] = None  # MIME type

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)  # Arbitrary metadata

    # Status
    is_valid: bool = True  # False if needs regeneration
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "item_id": self.item_id,
            "collection_id": self.collection_id,
            "step_name": self.step_name,
            "source_label": self.source_label,
            "version": self.version,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_format": self.file_format,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "mime_type": self.mime_type,
            "metadata": self.metadata,
            "is_valid": self.is_valid,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StepFile':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])

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


@dataclass
class TimelineEvent:
    """Timeline event for tracking activity history at item/collection level

    Enables:
    - Activity tracking: creation, processing, metadata changes, exports
    - Audit trail: who did what and when
    - User-facing timeline: show processing history to users
    - Analytics: understand workflow patterns

    Event Types:
    - created: Entity was created
    - processed: Processing workflow executed
    - metadata_added: New metadata version added
    - metadata_corrected: Metadata manually corrected
    - exported: Entity exported to file
    - imported: Entity imported from external source
    - status_changed: Status transition
    - error: Error occurred
    - custom: Custom event type

    Categories:
    - system: System-triggered events
    - user: User-triggered events
    - processing: Director/tool processing events
    - metadata: Metadata operations

    Actors:
    - system: Automatic system event
    - user:<username>: Specific user
    - tool:<tool_name>: Processing tool (crop, enhance, etc.)
    - ai:<model>: AI model (qwen, gpt, etc.)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: Literal["item", "collection"] = "item"  # What the event applies to
    entity_id: str = ""           # Item ID or Collection ID
    event_type: str = ""          # Event type (see docstring)
    event_category: str = ""      # Category: "system", "user", "processing", "metadata"
    actor: str = ""               # Who/what triggered (see docstring)
    description: str = ""         # Human-readable description
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional context
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'event_type': self.event_type,
            'event_category': self.event_category,
            'actor': self.actor,
            'description': self.description,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimelineEvent':
        """Create from dictionary"""
        # Handle datetime conversion
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])

        return cls(**data) 