"""
Document Data Model

Data model for document information extracted from manifests.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class DocumentData:
    """Document data model"""
    
    id: str
    title: str
    subtitle: str
    manifest_path: Path
    parent_dir: str
    modified: float
    size: int
    entry_count: int
    status: str
    
    @classmethod
    def from_manifest(cls, manifest_path: Path, doc_info: Dict[str, Any]) -> 'DocumentData':
        """Create DocumentData from manifest info"""
        return cls(
            id=doc_info.get('id', str(manifest_path)),
            title=doc_info.get('title', manifest_path.parent.name),
            subtitle=doc_info.get('subtitle', ''),
            manifest_path=manifest_path,
            parent_dir=doc_info.get('parent_dir', manifest_path.parent.name),
            modified=doc_info.get('modified', 0),
            size=doc_info.get('size', 0),
            entry_count=doc_info.get('entry_count', 0),
            status=doc_info.get('status', 'Unknown')
        )
    
    def to_list_data(self) -> Dict[str, Any]:
        """Convert to DetailedList format"""
        return {
            'title': self.title,
            'subtitle': f"{self.entry_count} entries • {self.status} • {self.subtitle}",
            'icon': self._get_status_icon(),
            'data': self
        }
    
    def _get_status_icon(self) -> Optional[str]:
        """Get appropriate icon for document status"""
        try:
            import toga
            if self.status == 'Processed':
                return toga.Icon("resources/icons/success")
            elif self.status == 'Failed':
                return toga.Icon("resources/icons/error")
            elif self.status == 'In Progress':
                return toga.Icon("resources/icons/processing")
            else:
                return toga.Icon("resources/icons/document")
        except Exception:
            return None 