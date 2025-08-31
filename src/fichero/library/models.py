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
    """Represents an individual item within a collection"""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str = ""
    type: Literal["file", "folder", "url", "camera", "audio"] = "file"
    source_path: Optional[str] = None
    local_path: Optional[str] = None
    storage_type: Literal["external", "local", "url"] = "external"
    name: str = ""
    status: Literal["pending", "processing", "completed", "error"] = "pending"
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