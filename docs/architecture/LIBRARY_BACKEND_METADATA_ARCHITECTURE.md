# Library Backend Metadata Storage Architecture

**Version:** 1.0
**Date:** November 15, 2025
**Status:** Design Document

## Executive Summary

This document defines a unified metadata storage architecture for the Fichero library backend. Currently, processing tools write step-level metadata directly to JSONL manifest files in output directories. This architecture centralizes all metadata in the SQLite library database, making it searchable, queryable, and version-aware while maintaining backwards compatibility with JSONL manifests.

### Key Goals

1. **Library backend as source of truth** - All step metadata stored in SQLite
2. **JSONL manifests as export format** - Library backend generates JSONL for backwards compatibility
3. **Unified tool API** - Consistent interface for storing/retrieving metadata
4. **Full searchability** - Query items by any metadata field
5. **Version tracking** - Track metadata changes over time
6. **Backwards compatibility** - Import existing JSONL metadata seamlessly

---

## 1. Current State Analysis

### 1.1 Existing Database Schema

The library backend (`src/fichero/library/`) already has sophisticated schema:

**Core Tables:**
- `collections` - Collection metadata with manual sorting
- `collection_items` - Items within collections (files, folders, URLs)
- `processing_history` - High-level workflow execution records
- `processing_outputs` - Individual output files from processing steps (NEW - already exists!)
- `extracted_metadata` - Searchable metadata from outputs (NEW - already exists!)
- `thumbnails` - Thumbnail deduplication tracking
- `external_paths` - External path monitoring

**Key Finding:** The schema ALREADY has `processing_outputs` and `extracted_metadata` tables! These were added recently but are not yet utilized by the tools.

### 1.2 Current Metadata Storage Patterns

#### JSONL Manifest Format (Current)

Tools write metadata to `*_manifest.jsonl` files with this structure:

```jsonl
{"source": "path/to/input.jpg", "outputs": ["path/to/output.jpg"], "details": {...}}
```

**Example - Crop Tool:**
```json
{
  "source": "documents/IMG_001.jpg",
  "outputs": ["prepared/IMG_001.jpg"],
  "details": {
    "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
    "method": "yolo",
    "confidence": 0.92,
    "padding": 30,
    "original_size": [1024, 768],
    "cropped_size": [700, 950],
    "rotation": {"reason": "EXIF rotation applied"},
    "attempts": [{"method": "yolo", "confidence": 0.35, "success": true}],
    "output_format": "jpg",
    "input_metadata": {"format": "JPEG", "mode": "RGB"}
  }
}
```

**Example - Rotate Tool:**
```json
{
  "source": "prepared/IMG_001.jpg",
  "outputs": ["rotated/IMG_001.jpg"],
  "details": {
    "original_size": [700, 950],
    "rotated_size": [700, 950],
    "debug": {
      "found_lines": true,
      "rotation_angle": -0.5,
      "num_lines": 42,
      "num_valid_angles": 38
    },
    "output_format": "jpg"
  }
}
```

**Example - Transcribe Tool:**
```json
{
  "source": "rotated/IMG_001.jpg",
  "outputs": ["transcriptions/IMG_001.txt"],
  "details": {
    "has_content": true,
    "text_length": 1247,
    "processed_at": "2025-11-15T14:30:00",
    "model": "qwen-vl-max",
    "num_lines": 42,
    "parent_info": {
      "path": "rotated/IMG_001.jpg",
      "original_size": "700x950"
    }
  }
}
```

**Example - Enhance Tool:**
```json
{
  "source": "prepared/IMG_001.jpg",
  "outputs": ["enhanced/IMG_001.jpg"],
  "details": {
    "document_type": "handwritten",
    "is_yellowed": 0.35,
    "enhancements_applied": ["clahe", "yellow_reduction", "sharpening"],
    "output_format": "jpg"
  }
}
```

### 1.3 Current Tool Inventory

| Tool | Step Name | Key Metadata Fields |
|------|-----------|---------------------|
| `crop.py` | `crop` | box, method, confidence, padding, rotation, attempts |
| `rotate.py` | `rotate` | rotation_angle, found_lines, num_lines, debug |
| `enhance.py` | `enhance` | document_type, is_yellowed, enhancements_applied |
| `transcribe_qwen_max.py` | `transcribe` | text_length, model, num_lines, has_content |
| `transcribe_lmstudio.py` | `transcribe` | text_length, model, num_lines, has_content |
| `remove_background.py` | `remove_background` | method, background_color, threshold |
| `split.py` | `split` | num_segments, split_method, segment_sizes |
| `segment.py` | `segment` | num_segments, segment_bounds |
| `recombine_segments.py` | `recombine` | num_segments_combined, final_size |
| `prepare_images.py` | `prepare_images` | preparation_steps, final_format |
| `convert_to_word.py` | `convert_to_word` | template_used, num_pages, word_version |
| `llm_process.py` | `catalogue_folder` | llm_model, prompt_used, fields_extracted |
| `json_to_word.py` | `json_to_word` | template_used, num_pages |
| `json_to_excel.py` | `json_to_excel` | num_rows, columns |
| `build_documents_manifest.py` | `build_manifest` | num_documents, file_types |

### 1.4 Gaps and Limitations

**Current System Limitations:**

1. **No searchability** - Can't query "all items cropped with YOLO" or "transcriptions longer than 1000 chars"
2. **Scattered metadata** - Each output folder has its own manifest files
3. **No version tracking** - Can't see metadata changes over time
4. **No bi-directional sync** - UI changes (e.g., manual crop adjustments) can't update library
5. **Duplicate storage** - Same metadata stored in both processing_history.metadata JSON blob AND JSONL files
6. **No structured queries** - Can't aggregate "average crop confidence" or "most common rotation angle"
7. **Import complexity** - Hard to import existing JSONL into library retroactively

**What's Missing:**

- API for tools to save step-level metadata to library
- Automatic JSONL generation from library data
- Import mechanism for existing JSONL manifests
- CLI commands for querying metadata
- Migration path for existing tools

---

## 2. Proposed Architecture

### 2.1 Core Principle: Dual Storage with Library as Source of Truth

```
┌─────────────────────────────────────────────────────────────┐
│                    Processing Tool                          │
│  (crop.py, rotate.py, transcribe.py, etc.)                 │
└────────────────┬────────────────────────────────────────────┘
                 │ 1. Save metadata via LibraryMetadataAPI
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              SQLite Library Backend                         │
│  ┌─────────────────┐  ┌──────────────────┐                 │
│  │ processing_     │  │ extracted_       │                 │
│  │ outputs         │  │ metadata         │                 │
│  │ - step_name     │  │ - metadata_type  │                 │
│  │ - output_path   │  │ - key            │                 │
│  │ - output_type   │  │ - value          │                 │
│  └─────────────────┘  └──────────────────┘                 │
│              │                                               │
│              │ 2. Generate JSONL on demand                  │
│              ▼                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │        JSONL Manifest Writer                        │   │
│  │  - Reads from library                               │   │
│  │  - Writes *_manifest.jsonl files                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                 │ 3. JSONL files for backwards compatibility
                 ▼
┌─────────────────────────────────────────────────────────────┐
│          Output Folders (assets/manifests/)                 │
│  - crop_manifest.jsonl                                      │
│  - rotate_manifest.jsonl                                    │
│  - transcriptions_manifest.jsonl                            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Database Schema Extensions

The existing `processing_outputs` and `extracted_metadata` tables need minor adjustments:

#### 2.2.1 Enhanced `processing_outputs` Table

```sql
-- ALREADY EXISTS - Just document usage pattern
CREATE TABLE processing_outputs (
    id TEXT PRIMARY KEY,
    processing_result_id TEXT NOT NULL,  -- FK to processing_history
    collection_id TEXT NOT NULL,          -- FK to collections
    item_id TEXT,                         -- FK to collection_items (NULL for batch)

    -- Step identification
    step_name TEXT NOT NULL,              -- e.g., "crop", "rotate", "transcribe"
    source_file TEXT,                     -- Relative path to input file

    -- Output tracking
    output_type TEXT NOT NULL,            -- "prepared_image", "transcription", "word_doc"
    output_path TEXT NOT NULL,            -- Relative path to output file
    file_format TEXT NOT NULL,            -- "jpg", "txt", "docx"
    file_size INTEGER,
    file_modified TEXT,

    -- Metadata tracking
    created_at TEXT NOT NULL,
    metadata_extracted INTEGER DEFAULT 0, -- Whether metadata was extracted
    is_valid INTEGER DEFAULT 1,           -- False if inputs changed

    -- Dependencies for re-running
    depends_on_output_ids TEXT,           -- JSON array of output IDs

    FOREIGN KEY (processing_result_id) REFERENCES processing_history(id),
    FOREIGN KEY (collection_id) REFERENCES collections(id),
    FOREIGN KEY (item_id) REFERENCES collection_items(id)
);

-- Indexes (already exist)
CREATE INDEX idx_processing_outputs_result_id ON processing_outputs(processing_result_id);
CREATE INDEX idx_processing_outputs_collection_id ON processing_outputs(collection_id);
CREATE INDEX idx_processing_outputs_item_id ON processing_outputs(item_id);
CREATE INDEX idx_processing_outputs_type ON processing_outputs(output_type);
CREATE INDEX idx_processing_outputs_step ON processing_outputs(step_name);
```

#### 2.2.2 Enhanced `extracted_metadata` Table

```sql
-- ALREADY EXISTS - Just document usage pattern
CREATE TABLE extracted_metadata (
    id TEXT PRIMARY KEY,
    processing_output_id TEXT NOT NULL,   -- FK to processing_outputs
    collection_id TEXT NOT NULL,          -- For easier querying
    item_id TEXT,                         -- For file-level metadata

    -- Metadata content
    metadata_type TEXT NOT NULL,          -- "step_param", "step_result", "transcription", "entity"
    key TEXT NOT NULL,                    -- Field name: "crop.method", "rotate.angle", "text"
    value TEXT NOT NULL,                  -- The actual data (JSON for complex values)

    -- AI-extracted data
    confidence REAL,                      -- 0.0-1.0 for AI-extracted data
    context TEXT,                         -- Surrounding context for quotes/entities

    -- Indexing
    indexed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,

    FOREIGN KEY (processing_output_id) REFERENCES processing_outputs(id),
    FOREIGN KEY (collection_id) REFERENCES collections(id),
    FOREIGN KEY (item_id) REFERENCES collection_items(id)
);

-- Indexes (already exist)
CREATE INDEX idx_extracted_metadata_output_id ON extracted_metadata(processing_output_id);
CREATE INDEX idx_extracted_metadata_collection_id ON extracted_metadata(collection_id);
CREATE INDEX idx_extracted_metadata_type ON extracted_metadata(metadata_type);
CREATE INDEX idx_extracted_metadata_key ON extracted_metadata(key);
CREATE INDEX idx_extracted_metadata_value ON extracted_metadata(value);
```

#### 2.2.3 New Table: `step_metadata_versions`

Track metadata changes over time for version control:

```sql
CREATE TABLE step_metadata_versions (
    id TEXT PRIMARY KEY,
    processing_output_id TEXT NOT NULL,
    version INTEGER NOT NULL,             -- Sequential version number

    -- Change tracking
    changed_at TEXT NOT NULL,
    changed_by TEXT,                      -- "tool", "user", "system"
    change_reason TEXT,                   -- "initial", "manual_edit", "reprocessed"

    -- Snapshot of metadata at this version
    metadata_snapshot TEXT NOT NULL,      -- JSON blob of all metadata at this version

    FOREIGN KEY (processing_output_id) REFERENCES processing_outputs(id)
);

CREATE INDEX idx_step_metadata_versions_output_id ON step_metadata_versions(processing_output_id);
CREATE INDEX idx_step_metadata_versions_changed_at ON step_metadata_versions(changed_at);
```

### 2.3 Metadata Type Taxonomy

Define standard `metadata_type` values for `extracted_metadata` table:

| Metadata Type | Description | Example Keys |
|---------------|-------------|--------------|
| `step_param` | Input parameters to a tool step | `crop.padding`, `rotate.blur_kernel`, `transcribe.model` |
| `step_result` | Output results from a tool step | `crop.box`, `crop.confidence`, `rotate.angle`, `enhance.document_type` |
| `transcription` | Extracted text content | `text`, `text_length`, `num_lines` |
| `detection` | Detection/recognition results | `crop.method`, `crop.attempts`, `rotate.found_lines` |
| `file_info` | File-level metadata | `output_format`, `file_size`, `original_size` |
| `entity` | AI-extracted entities | `person_name`, `place`, `date` (future use) |
| `catalogue_field` | Catalogue metadata | `title`, `description`, `author` (from llm_process) |

### 2.4 Step Metadata Schema (JSON Structure)

For each tool, define the metadata fields stored in `extracted_metadata`:

#### Crop Tool Metadata

```json
{
  "step_params": {
    "padding": 30,
    "contour_settings": {...}
  },
  "step_results": {
    "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
    "method": "yolo",
    "confidence": 0.92,
    "original_size": [1024, 768],
    "cropped_size": [700, 950]
  },
  "detection": {
    "attempts": [
      {"method": "yolo", "confidence": 0.35, "success": true}
    ],
    "rotation": {"reason": "EXIF rotation applied"}
  },
  "file_info": {
    "output_format": "jpg",
    "input_metadata": {"format": "JPEG", "mode": "RGB"}
  }
}
```

Stored as:
```sql
INSERT INTO extracted_metadata VALUES
  ('uuid1', 'output_id', 'coll_id', 'item_id', 'step_param', 'crop.padding', '30', NULL, NULL, 0, '2025-11-15T14:30:00'),
  ('uuid2', 'output_id', 'coll_id', 'item_id', 'step_result', 'crop.box', '{"x1":100,"y1":50,"x2":800,"y2":1000}', NULL, NULL, 0, '2025-11-15T14:30:00'),
  ('uuid3', 'output_id', 'coll_id', 'item_id', 'step_result', 'crop.method', 'yolo', 0.92, NULL, 0, '2025-11-15T14:30:00'),
  ...
```

---

## 3. API Design

### 3.1 LibraryMetadataAPI Interface

Create a new module: `src/fichero/library/metadata_api.py`

```python
"""
Library Metadata API

Unified interface for tools to store and retrieve step-level metadata.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging

from fichero.library.models import ProcessingOutput, ExtractedMetadata
from fichero.library.storage import LibraryStorage

logger = logging.getLogger(__name__)


class LibraryMetadataAPI:
    """
    API for storing and retrieving step-level metadata in library backend.

    Usage by tools:
        api = LibraryMetadataAPI(library_storage)
        api.save_step_metadata(
            processing_result_id="result-123",
            collection_id="coll-456",
            item_id="item-789",
            step_name="crop",
            source_file="documents/IMG_001.jpg",
            output_file="prepared/IMG_001.jpg",
            output_type="prepared_image",
            metadata={
                "step_params": {"padding": 30},
                "step_results": {"box": {...}, "method": "yolo", "confidence": 0.92},
                "detection": {"attempts": [...]},
                "file_info": {"output_format": "jpg"}
            }
        )
    """

    def __init__(self, storage: LibraryStorage):
        self.storage = storage

    def save_step_metadata(
        self,
        processing_result_id: str,
        collection_id: str,
        step_name: str,
        source_file: str,
        output_file: str,
        output_type: str,
        metadata: Dict[str, Any],
        item_id: Optional[str] = None,
        file_size: Optional[int] = None,
        file_modified: Optional[datetime] = None
    ) -> str:
        """
        Save metadata for a processing step.

        Args:
            processing_result_id: ID of the ProcessingResult this belongs to
            collection_id: ID of the collection
            step_name: Name of the processing step (e.g., "crop", "rotate")
            source_file: Relative path to input file
            output_file: Relative path to output file
            output_type: Type of output ("prepared_image", "transcription", etc.)
            metadata: Structured metadata dict with keys:
                - step_params: Input parameters
                - step_results: Output results
                - detection: Detection/recognition results
                - file_info: File metadata
            item_id: Optional item ID for file-level outputs
            file_size: Optional output file size in bytes
            file_modified: Optional output file modification time

        Returns:
            output_id: ID of the created ProcessingOutput record
        """
        # 1. Create ProcessingOutput record
        output = ProcessingOutput(
            processing_result_id=processing_result_id,
            collection_id=collection_id,
            item_id=item_id,
            step_name=step_name,
            source_file=source_file,
            output_type=output_type,
            output_path=output_file,
            file_format=Path(output_file).suffix.lstrip('.'),
            file_size=file_size,
            file_modified=file_modified,
            created_at=datetime.now(),
            metadata_extracted=True,
            is_valid=True
        )

        success = self.storage.add_processing_output(output)
        if not success:
            raise RuntimeError(f"Failed to save processing output for {step_name}")

        # 2. Extract and save metadata entries
        self._extract_and_save_metadata(
            output_id=output.id,
            collection_id=collection_id,
            item_id=item_id,
            step_name=step_name,
            metadata=metadata
        )

        # 3. Create initial version snapshot
        self._create_version_snapshot(
            output_id=output.id,
            metadata=metadata,
            changed_by="tool",
            change_reason="initial"
        )

        logger.info(f"Saved metadata for {step_name}: {output_file}")
        return output.id

    def _extract_and_save_metadata(
        self,
        output_id: str,
        collection_id: str,
        item_id: Optional[str],
        step_name: str,
        metadata: Dict[str, Any]
    ):
        """Extract metadata entries from structured dict and save to database."""

        # Process each metadata category
        for category, fields in metadata.items():
            metadata_type = self._category_to_type(category)

            if isinstance(fields, dict):
                for key, value in fields.items():
                    self._save_metadata_entry(
                        output_id=output_id,
                        collection_id=collection_id,
                        item_id=item_id,
                        metadata_type=metadata_type,
                        key=f"{step_name}.{key}",
                        value=value
                    )
            elif isinstance(fields, (str, int, float, bool)):
                # Simple value
                self._save_metadata_entry(
                    output_id=output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    metadata_type=metadata_type,
                    key=f"{step_name}.{category}",
                    value=fields
                )

    def _category_to_type(self, category: str) -> str:
        """Map metadata category to metadata_type."""
        mapping = {
            "step_params": "step_param",
            "step_results": "step_result",
            "detection": "detection",
            "file_info": "file_info",
            "transcription": "transcription",
            "catalogue": "catalogue_field"
        }
        return mapping.get(category, "step_result")

    def _save_metadata_entry(
        self,
        output_id: str,
        collection_id: str,
        item_id: Optional[str],
        metadata_type: str,
        key: str,
        value: Any,
        confidence: Optional[float] = None
    ):
        """Save a single metadata entry."""

        # Serialize complex values to JSON
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value, ensure_ascii=False)
        else:
            value_str = str(value)

        # Extract confidence if present in value
        if isinstance(value, dict) and "confidence" in value:
            confidence = value.get("confidence")

        metadata = ExtractedMetadata(
            processing_output_id=output_id,
            collection_id=collection_id,
            item_id=item_id,
            metadata_type=metadata_type,
            key=key,
            value=value_str,
            confidence=confidence,
            created_at=datetime.now()
        )

        self.storage.add_extracted_metadata(metadata)

    def _create_version_snapshot(
        self,
        output_id: str,
        metadata: Dict[str, Any],
        changed_by: str,
        change_reason: str
    ):
        """Create a version snapshot of metadata."""
        # Get current version count
        # TODO: Implement version tracking in storage.py
        version = 1

        snapshot = {
            "version": version,
            "changed_at": datetime.now().isoformat(),
            "changed_by": changed_by,
            "change_reason": change_reason,
            "metadata": metadata
        }

        # TODO: Add to step_metadata_versions table
        logger.debug(f"Created version snapshot v{version} for output {output_id}")

    def get_step_metadata(
        self,
        output_id: str
    ) -> Dict[str, Any]:
        """
        Get all metadata for a processing output.

        Args:
            output_id: ID of the ProcessingOutput

        Returns:
            Structured metadata dict with categories
        """
        metadata_entries = self.storage.get_extracted_metadata(output_id)

        # Reconstruct structured metadata
        result = {
            "step_params": {},
            "step_results": {},
            "detection": {},
            "file_info": {},
            "transcription": {},
            "catalogue": {}
        }

        for entry in metadata_entries:
            category = self._type_to_category(entry.metadata_type)

            # Extract step name from key (e.g., "crop.box" -> "box")
            key_parts = entry.key.split('.', 1)
            if len(key_parts) == 2:
                field_name = key_parts[1]
            else:
                field_name = entry.key

            # Deserialize JSON values
            try:
                value = json.loads(entry.value)
            except (json.JSONDecodeError, TypeError):
                value = entry.value

            result[category][field_name] = value

        return result

    def _type_to_category(self, metadata_type: str) -> str:
        """Map metadata_type to category."""
        mapping = {
            "step_param": "step_params",
            "step_result": "step_results",
            "detection": "detection",
            "file_info": "file_info",
            "transcription": "transcription",
            "catalogue_field": "catalogue"
        }
        return mapping.get(metadata_type, "step_results")

    def query_items_by_metadata(
        self,
        collection_id: str,
        filters: Dict[str, Any]
    ) -> List[str]:
        """
        Query items by metadata filters.

        Args:
            collection_id: Collection to query
            filters: Dict of key-value filters, e.g.:
                {
                    "crop.method": "yolo",
                    "crop.confidence": {"$gte": 0.8},
                    "transcribe.text_length": {"$gte": 1000}
                }

        Returns:
            List of item IDs matching filters
        """
        # TODO: Implement complex query logic
        # For now, simple equality matching

        matching_items = set()

        for key, value in filters.items():
            # Search metadata
            if isinstance(value, dict):
                # Complex filter (e.g., {"$gte": 0.8})
                # TODO: Implement operator parsing
                pass
            else:
                # Simple equality
                results = self.storage.search_metadata(
                    collection_id=collection_id,
                    query=str(value),
                    key=key
                )

                item_ids = {m.item_id for m in results if m.item_id}

                if not matching_items:
                    matching_items = item_ids
                else:
                    matching_items &= item_ids  # Intersection (AND logic)

        return list(matching_items)

    def update_step_metadata(
        self,
        output_id: str,
        updates: Dict[str, Any],
        changed_by: str = "user"
    ):
        """
        Update specific metadata fields and create new version.

        Args:
            output_id: ID of the ProcessingOutput
            updates: Dict of field updates, e.g.:
                {"crop.box": {"x1": 110, "y1": 60, "x2": 810, "y2": 1010}}
            changed_by: Who made the change ("user", "tool", "system")
        """
        # TODO: Implement update logic with versioning
        pass
```

### 3.2 JSONL Sync API

Create a new module: `src/fichero/library/jsonl_sync.py`

```python
"""
JSONL Manifest Sync

Generates JSONL manifest files from library backend data.
Also imports existing JSONL manifests into library.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging

from fichero.library.storage import LibraryStorage
from fichero.library.metadata_api import LibraryMetadataAPI

logger = logging.getLogger(__name__)


class JSONLSync:
    """
    Handles bi-directional sync between library backend and JSONL manifests.
    """

    def __init__(self, storage: LibraryStorage):
        self.storage = storage
        self.metadata_api = LibraryMetadataAPI(storage)

    def export_to_jsonl(
        self,
        processing_result_id: str,
        output_folder: Path,
        step_name: str
    ) -> Path:
        """
        Export processing outputs to JSONL manifest file.

        Args:
            processing_result_id: ID of the ProcessingResult
            output_folder: Folder to write manifest to
            step_name: Name of the step (e.g., "crop")

        Returns:
            Path to created manifest file
        """
        # Get all outputs for this processing result
        outputs = self.storage.get_processing_outputs(processing_result_id)

        # Filter by step name
        step_outputs = [o for o in outputs if o.step_name == step_name]

        # Create manifest path
        manifest_path = output_folder / f"{step_name}_manifest.jsonl"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # Write JSONL entries
        with open(manifest_path, 'w', encoding='utf-8') as f:
            for output in step_outputs:
                entry = self._create_jsonl_entry(output)
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        logger.info(f"Exported {len(step_outputs)} entries to {manifest_path}")
        return manifest_path

    def _create_jsonl_entry(self, output: 'ProcessingOutput') -> Dict[str, Any]:
        """Create JSONL entry from ProcessingOutput and metadata."""

        # Get metadata for this output
        metadata = self.metadata_api.get_step_metadata(output.id)

        # Flatten metadata into "details" dict (backwards compatibility)
        details = {}
        for category, fields in metadata.items():
            if fields:
                if category == "step_params":
                    # Include params at top level of details
                    details.update(fields)
                elif category == "step_results":
                    # Include results at top level
                    details.update(fields)
                else:
                    # Nest other categories
                    details[category] = fields

        entry = {
            "source": output.source_file,
            "outputs": [output.output_path],
            "tool": output.step_name
        }

        if details:
            entry["details"] = details

        return entry

    def import_from_jsonl(
        self,
        manifest_path: Path,
        processing_result_id: str,
        collection_id: str,
        step_name: str
    ) -> int:
        """
        Import existing JSONL manifest into library backend.

        Args:
            manifest_path: Path to JSONL manifest file
            processing_result_id: ID of the ProcessingResult to link to
            collection_id: ID of the collection
            step_name: Name of the step

        Returns:
            Number of entries imported
        """
        if not manifest_path.exists():
            logger.warning(f"Manifest not found: {manifest_path}")
            return 0

        count = 0
        with open(manifest_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    self._import_jsonl_entry(
                        entry,
                        processing_result_id,
                        collection_id,
                        step_name
                    )
                    count += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSONL line: {e}")
                except Exception as e:
                    logger.error(f"Failed to import entry: {e}")

        logger.info(f"Imported {count} entries from {manifest_path}")
        return count

    def _import_jsonl_entry(
        self,
        entry: Dict[str, Any],
        processing_result_id: str,
        collection_id: str,
        step_name: str
    ):
        """Import a single JSONL entry."""

        source = entry.get("source")
        outputs = entry.get("outputs", [])
        details = entry.get("details", {})

        if not source or not outputs:
            logger.warning("Entry missing source or outputs, skipping")
            return

        # Use first output (most tools have single output)
        output_file = outputs[0] if isinstance(outputs, list) else outputs

        # Infer output type from step name
        output_type_map = {
            "crop": "prepared_image",
            "rotate": "prepared_image",
            "enhance": "prepared_image",
            "transcribe": "transcription",
            "convert_to_word": "word_doc",
            "catalogue_folder": "catalogue"
        }
        output_type = output_type_map.get(step_name, "unknown")

        # Restructure details into metadata categories
        metadata = self._restructure_details(details, step_name)

        # Save to library
        self.metadata_api.save_step_metadata(
            processing_result_id=processing_result_id,
            collection_id=collection_id,
            step_name=step_name,
            source_file=source,
            output_file=output_file,
            output_type=output_type,
            metadata=metadata
        )

    def _restructure_details(
        self,
        details: Dict[str, Any],
        step_name: str
    ) -> Dict[str, Any]:
        """Restructure flat details dict into categorized metadata."""

        # Define which fields go into which category for each tool
        categorization = {
            "crop": {
                "step_params": ["padding", "contour_settings"],
                "step_results": ["box", "method", "confidence", "original_size", "cropped_size"],
                "detection": ["attempts", "rotation"],
                "file_info": ["output_format", "input_metadata"]
            },
            "rotate": {
                "step_results": ["rotation_angle", "original_size", "rotated_size"],
                "detection": ["debug", "found_lines", "num_lines"],
                "file_info": ["output_format"]
            },
            "transcribe": {
                "step_results": ["model", "num_lines", "has_content", "text_length"],
                "transcription": ["text", "processed_at"],
                "file_info": ["parent_info"]
            }
        }

        categories = categorization.get(step_name, {})

        metadata = {
            "step_params": {},
            "step_results": {},
            "detection": {},
            "file_info": {},
            "transcription": {}
        }

        # Categorize fields
        for field, value in details.items():
            placed = False
            for category, fields in categories.items():
                if field in fields:
                    metadata[category][field] = value
                    placed = True
                    break

            if not placed:
                # Default to step_results
                metadata["step_results"][field] = value

        return metadata
```

---

## 4. JSONL Sync Strategy

### 4.1 When to Generate JSONL

**Option 1: On-Demand Generation (Recommended)**
- JSONL files generated only when requested
- Reduces I/O overhead during processing
- Always reflects current library state

**Option 2: Real-Time Sync**
- JSONL files updated immediately after library writes
- Ensures JSONL always exists for backwards compatibility
- Higher I/O overhead

**Recommendation:** Start with Option 1 (on-demand), add Option 2 later if needed.

### 4.2 Import Strategy

**Scenario 1: New Processing (Fresh)**
- Tools save metadata to library via LibraryMetadataAPI
- JSONL generated on-demand if needed

**Scenario 2: Existing JSONL Files (Migration)**
- Use `jsonl_sync.import_from_jsonl()` to load existing manifests
- One-time migration script scans output folders
- Preserves all historical metadata

**Scenario 3: External JSONL (User-Provided)**
- Import API validates and sanitizes external JSONL
- Links to appropriate collection/processing result

### 4.3 Backwards Compatibility

- Existing tools continue writing JSONL directly (Phase 4)
- New tools use LibraryMetadataAPI + JSONL export (Phase 3)
- Gradual migration tool by tool
- JSONL format remains unchanged for external consumers

---

## 5. Tool Integration Pattern

### 5.1 Before: Direct JSONL Writing

```python
# OLD: Direct JSONL writing (crop.py example)
def process_image(file_path: Path, out_path: Path, **kwargs) -> dict:
    # ... process image ...

    crop_info_dict = crop_info.to_dict()
    crop_info_dict["attempts"] = attempts
    crop_info_dict["output_format"] = actual_format

    return {
        "outputs": [str(output_rel_path)],
        "source": str(rel_path),
        "details": crop_info_dict
    }

# BatchProcessor writes this dict to JSONL manifest
```

### 5.2 After: Library + JSONL Sync

```python
# NEW: Library metadata storage with optional JSONL export

# Step 1: Import LibraryMetadataAPI
from fichero.library.metadata_api import LibraryMetadataAPI
from fichero.library.storage import LibraryStorage

# Step 2: Initialize API (passed from workflow executor)
def process_image(
    file_path: Path,
    out_path: Path,
    metadata_api: Optional[LibraryMetadataAPI] = None,  # NEW parameter
    processing_context: Optional[Dict] = None,          # NEW parameter
    **kwargs
) -> dict:
    # ... process image ...

    # Prepare metadata
    metadata = {
        "step_params": {
            "padding": kwargs.get("padding", 30),
            "contour_settings": kwargs.get("contour_settings", {})
        },
        "step_results": {
            "box": crop_info.box,
            "method": crop_info.method,
            "confidence": crop_info.confidence,
            "original_size": crop_info.original_size,
            "cropped_size": crop_info.cropped_size
        },
        "detection": {
            "attempts": attempts,
            "rotation": crop_info.rotation
        },
        "file_info": {
            "output_format": actual_format,
            "input_metadata": metadata
        }
    }

    # Save to library if API provided
    if metadata_api and processing_context:
        metadata_api.save_step_metadata(
            processing_result_id=processing_context["result_id"],
            collection_id=processing_context["collection_id"],
            item_id=processing_context.get("item_id"),
            step_name="crop",
            source_file=str(rel_path),
            output_file=str(output_rel_path),
            output_type="prepared_image",
            metadata=metadata
        )

    # Return dict for backwards compatibility with JSONL
    return {
        "outputs": [str(output_rel_path)],
        "source": str(rel_path),
        "details": {
            **metadata["step_results"],
            **metadata["detection"],
            **metadata["file_info"]
        }
    }
```

### 5.3 Workflow Executor Integration

The Director's workflow executor needs to:

1. Create a ProcessingResult record at workflow start
2. Initialize LibraryMetadataAPI with library storage
3. Pass `metadata_api` and `processing_context` to tools
4. Export JSONL manifests after workflow completes (optional)

```python
# In director/folder_processor.py or similar

def execute_workflow(collection_id: str, item_id: str, workflow_config: Dict):
    # 1. Create ProcessingResult
    result = ProcessingResult(
        item_id=item_id,
        workflow=workflow_config["name"],
        status="running",
        started_at=datetime.now()
    )
    library.storage.add_processing_result(result)

    # 2. Initialize metadata API
    metadata_api = LibraryMetadataAPI(library.storage)

    # 3. Prepare context for tools
    processing_context = {
        "result_id": result.id,
        "collection_id": collection_id,
        "item_id": item_id
    }

    # 4. Execute workflow steps with metadata API
    for step in workflow_config["steps"]:
        tool_function = get_tool(step["tool"])
        tool_function(
            **step["params"],
            metadata_api=metadata_api,
            processing_context=processing_context
        )

    # 5. Mark result as complete
    result.status = "success"
    result.completed_at = datetime.now()
    library.storage.update_processing_result(result)

    # 6. Optionally export JSONL manifests
    if should_export_jsonl:
        jsonl_sync = JSONLSync(library.storage)
        for step in workflow_config["steps"]:
            jsonl_sync.export_to_jsonl(
                processing_result_id=result.id,
                output_folder=output_folder,
                step_name=step["tool"]
            )
```

---

## 6. Migration Strategy

### Phase 1: Core Library Backend API (Week 1)

**Deliverables:**
1. Add `step_metadata_versions` table to schema
2. Implement `LibraryMetadataAPI` in `src/fichero/library/metadata_api.py`
3. Add version snapshot creation
4. Unit tests for metadata storage/retrieval

**Testing:**
- Test metadata save/retrieve with mock data
- Verify version tracking works correctly
- Validate metadata categorization

### Phase 2: JSONL Sync Layer (Week 1-2)

**Deliverables:**
1. Implement `JSONLSync` in `src/fichero/library/jsonl_sync.py`
2. JSONL export from library data
3. JSONL import into library
4. Migration script for existing manifests

**Testing:**
- Test JSONL export produces correct format
- Test JSONL import preserves all metadata
- Validate round-trip consistency (export → import → export)

### Phase 3: CLI Testing Interface (Week 2)

**Deliverables:**
1. Add CLI commands to `src/fichero/cli/library_cli.py`:
   - `briefcase dev -- library metadata-import <collection_id> <manifest_path>`
   - `briefcase dev -- library metadata-export <collection_id> <output_folder>`
   - `briefcase dev -- library metadata-query <collection_id> <filters>`
   - `briefcase dev -- library metadata-stats <collection_id>`

**Testing:**
- Manual CLI testing with sample collections
- Query metadata by different filters
- Verify export/import workflows

### Phase 4: Tool Migration (Week 3-4)

**Migration Order (Priority):**

1. **crop.py** (High metadata complexity)
   - Most complex metadata structure
   - Good test case for system

2. **rotate.py** (Simple metadata)
   - Simple structure, quick win

3. **transcribe_qwen_max.py** (Text content)
   - Tests transcription metadata storage

4. **enhance.py** (Analysis results)
   - Tests detection metadata

5. **convert_to_word.py** (Document generation)
   - Tests output metadata

6. **llm_process.py** (Catalogue fields)
   - Tests catalogue metadata extraction

**Per-Tool Migration Steps:**

1. Add `metadata_api` and `processing_context` parameters to tool function
2. Restructure metadata into categories (step_params, step_results, etc.)
3. Call `metadata_api.save_step_metadata()`
4. Keep backwards-compatible JSONL return format
5. Test with sample data
6. Update workflow executor to pass metadata API

### Phase 5: Search & Query Features (Week 4-5)

**Deliverables:**
1. Advanced query operators ($gte, $lte, $in, $contains)
2. Aggregation queries (average confidence, text length distribution)
3. Full-text search on transcriptions
4. GUI search interface integration

---

## 7. Code Examples

### 7.1 CLI Usage Examples

```bash
# Import existing JSONL manifests into library
briefcase dev -- library metadata-import <collection_id> /path/to/output/assets/manifests/

# Export metadata to JSONL
briefcase dev -- library metadata-export <collection_id> /path/to/export/

# Query items by metadata
briefcase dev -- library metadata-query <collection_id> 'crop.method=yolo'
briefcase dev -- library metadata-query <collection_id> 'crop.confidence>=0.8'
briefcase dev -- library metadata-query <collection_id> 'transcribe.text_length>=1000'

# Get metadata statistics
briefcase dev -- library metadata-stats <collection_id>
# Output:
#   Crop Statistics:
#     - Total cropped: 42
#     - YOLO detections: 38 (90.5%)
#     - Contour detections: 3 (7.1%)
#     - Fallback (original): 1 (2.4%)
#     - Average confidence: 0.87
#
#   Transcription Statistics:
#     - Total transcribed: 42
#     - Average text length: 847 chars
#     - Average lines: 28
#     - Empty transcriptions: 2

# Search transcriptions
briefcase dev -- library metadata-search <collection_id> "search term"
```

### 7.2 Python API Examples

```python
# Get metadata for an item
from fichero.library.library_manager import LibraryManager
from fichero.library.metadata_api import LibraryMetadataAPI

library = LibraryManager()
metadata_api = LibraryMetadataAPI(library.storage)

# Get outputs for an item
outputs = library.storage.get_outputs_by_item(item_id)

# Get metadata for crop step
crop_output = next((o for o in outputs if o.step_name == "crop"), None)
if crop_output:
    metadata = metadata_api.get_step_metadata(crop_output.id)
    print(f"Crop method: {metadata['step_results']['method']}")
    print(f"Confidence: {metadata['step_results']['confidence']}")
    print(f"Box: {metadata['step_results']['box']}")

# Query items
items = metadata_api.query_items_by_metadata(
    collection_id="coll-123",
    filters={
        "crop.method": "yolo",
        "crop.confidence": {"$gte": 0.8}
    }
)
print(f"Found {len(items)} items with high-confidence YOLO crops")

# Search transcriptions
results = library.storage.search_metadata(
    collection_id="coll-123",
    query="important document",
    metadata_type="transcription"
)
for result in results:
    print(f"Item {result.item_id}: {result.value[:100]}...")
```

### 7.3 Tool Integration Example (Complete)

Here's a complete example showing how to migrate the crop tool:

```python
# src/fichero/tools/crop.py (migrated)

from typing import Optional, Dict, Any
from pathlib import Path

try:
    from fichero.library.metadata_api import LibraryMetadataAPI
except ImportError:
    LibraryMetadataAPI = None  # Allow standalone usage

def process_image(
    file_path: Path,
    out_path: Path,
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS,
    # NEW: Library integration parameters
    metadata_api: Optional[LibraryMetadataAPI] = None,
    processing_context: Optional[Dict[str, Any]] = None,
) -> dict:
    """
    Process a single image file.

    Args:
        file_path: Input image path
        out_path: Output image path
        output_format: Output format (jpg, png, jxl)
        contour_settings: Contour detection settings
        metadata_api: Optional library metadata API for saving metadata
        processing_context: Optional context dict with:
            - result_id: ProcessingResult ID
            - collection_id: Collection ID
            - item_id: Item ID (optional)

    Returns:
        Dict with outputs, source, and details (JSONL compatible)
    """
    # ... existing processing code ...

    # Prepare structured metadata
    metadata = {
        "step_params": {
            "padding": contour_settings.padding,
            "output_format": output_format,
            "contour_settings": contour_settings.to_dict() if contour_settings else None
        },
        "step_results": {
            "box": crop_info.box,
            "method": crop_info.method,
            "confidence": crop_info.confidence,
            "original_size": crop_info.original_size,
            "cropped_size": crop_info.cropped_size
        },
        "detection": {
            "attempts": attempts,
            "rotation": crop_info.rotation
        },
        "file_info": {
            "output_format": actual_format,
            "input_metadata": metadata
        }
    }

    # Save to library if API provided
    if metadata_api and processing_context:
        try:
            # Get file size
            file_size = final_path.stat().st_size if final_path.exists() else None
            file_modified = datetime.fromtimestamp(final_path.stat().st_mtime) if final_path.exists() else None

            metadata_api.save_step_metadata(
                processing_result_id=processing_context["result_id"],
                collection_id=processing_context["collection_id"],
                item_id=processing_context.get("item_id"),
                step_name="crop",
                source_file=str(rel_path),
                output_file=str(output_rel_path),
                output_type="prepared_image",
                metadata=metadata,
                file_size=file_size,
                file_modified=file_modified
            )
            tool_logger.info(f"Saved crop metadata to library for {file_path.name}")
        except Exception as e:
            tool_logger.error(f"Failed to save metadata to library: {e}")
            # Continue processing even if library save fails

    # Return backwards-compatible JSONL format
    crop_info_dict = crop_info.to_dict()
    crop_info_dict["attempts"] = attempts
    crop_info_dict["output_format"] = actual_format
    crop_info_dict["input_metadata"] = metadata

    return {
        "outputs": [str(output_rel_path)],
        "source": str(rel_path),
        "details": crop_info_dict
    }
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

**Test Suite: `tests/test_metadata_api.py`**

```python
import pytest
from pathlib import Path
from fichero.library.storage import LibraryStorage
from fichero.library.metadata_api import LibraryMetadataAPI
from fichero.library.models import ProcessingResult

def test_save_step_metadata(tmp_path):
    """Test saving step metadata to library."""
    # Setup
    db_path = tmp_path / "test.db"
    storage = LibraryStorage(db_path)
    api = LibraryMetadataAPI(storage)

    # Create test processing result
    result = ProcessingResult(
        item_id="item-123",
        workflow="test",
        status="success"
    )
    storage.add_processing_result(result)

    # Save metadata
    metadata = {
        "step_params": {"padding": 30},
        "step_results": {
            "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
            "method": "yolo",
            "confidence": 0.92
        }
    }

    output_id = api.save_step_metadata(
        processing_result_id=result.id,
        collection_id="coll-456",
        step_name="crop",
        source_file="documents/IMG_001.jpg",
        output_file="prepared/IMG_001.jpg",
        output_type="prepared_image",
        metadata=metadata
    )

    # Verify
    assert output_id is not None
    retrieved = api.get_step_metadata(output_id)
    assert retrieved["step_results"]["method"] == "yolo"
    assert retrieved["step_results"]["confidence"] == 0.92

def test_query_items_by_metadata(tmp_path):
    """Test querying items by metadata filters."""
    # Setup and add test data...

    # Query
    items = api.query_items_by_metadata(
        collection_id="coll-456",
        filters={
            "crop.method": "yolo",
            "crop.confidence": {"$gte": 0.8}
        }
    )

    assert len(items) == 2  # Should match 2 items
```

### 8.2 Integration Tests

**Test Suite: `tests/test_jsonl_sync.py`**

```python
def test_export_import_roundtrip(tmp_path):
    """Test JSONL export → import preserves metadata."""
    # Setup library with metadata
    # Export to JSONL
    # Import into new library
    # Compare metadata equality
    pass

def test_import_legacy_jsonl(tmp_path):
    """Test importing existing JSONL manifests."""
    # Create legacy JSONL file
    # Import into library
    # Verify all fields preserved
    pass
```

### 8.3 CLI Testing

**Manual Test Plan:**

1. Create test collection with sample images
2. Process with crop tool (generates JSONL)
3. Import JSONL into library: `briefcase dev -- library metadata-import <coll_id> <manifest_path>`
4. Query metadata: `briefcase dev -- library metadata-query <coll_id> 'crop.method=yolo'`
5. Export back to JSONL: `briefcase dev -- library metadata-export <coll_id> <output_path>`
6. Compare original and exported JSONL (should be identical)

### 8.4 Migration Validation

**Test Plan:**

1. Select 5 existing output folders with JSONL manifests
2. Import all manifests into library
3. Query metadata to verify completeness
4. Export back to JSONL
5. Diff original vs exported JSONL files
6. Manually inspect differences (should only be ordering/formatting)

---

## 9. Implementation Phases (Detailed Timeline)

### Week 1: Core Infrastructure

**Days 1-2: Database Schema**
- Add `step_metadata_versions` table
- Migration script for existing databases
- Verify indexes and foreign keys

**Days 3-5: LibraryMetadataAPI**
- Implement save/get/query methods
- Version tracking
- Unit tests (80% coverage target)

**Days 6-7: Code Review & Documentation**
- API documentation
- Usage examples
- Performance testing

### Week 2: JSONL Sync & CLI

**Days 8-10: JSONLSync**
- Export functionality
- Import functionality
- Round-trip tests

**Days 11-12: CLI Commands**
- `metadata-import` command
- `metadata-export` command
- `metadata-query` command
- `metadata-stats` command

**Days 13-14: Integration Testing**
- End-to-end tests
- Migration script for existing data
- Performance profiling

### Week 3-4: Tool Migration

**Week 3:**
- Migrate crop.py
- Migrate rotate.py
- Migrate transcribe_qwen_max.py
- Integration testing for each

**Week 4:**
- Migrate enhance.py
- Migrate convert_to_word.py
- Migrate llm_process.py
- Full workflow testing

### Week 5: Search & Optimization

**Days 29-31: Advanced Query Features**
- Operator support ($gte, $lte, etc.)
- Aggregation queries
- Full-text search

**Days 32-35: Performance Optimization**
- Query optimization
- Index tuning
- Caching layer (if needed)
- Load testing

---

## 10. Success Criteria

### Functional Requirements

- [ ] All processing metadata stored in SQLite library backend
- [ ] JSONL manifests generated from library data
- [ ] Existing JSONL manifests can be imported
- [ ] Tools can save metadata via unified API
- [ ] Metadata is searchable via CLI and Python API
- [ ] Version tracking works for metadata changes

### Non-Functional Requirements

- [ ] Metadata save/retrieve < 10ms per operation
- [ ] Query performance < 100ms for typical filters
- [ ] JSONL export/import < 1s for 1000 entries
- [ ] 90%+ test coverage for new code
- [ ] Zero data loss during migration
- [ ] Backwards compatible with existing JSONL consumers

### Migration Requirements

- [ ] All 6 priority tools migrated successfully
- [ ] Existing JSONL metadata imported completely
- [ ] Round-trip consistency (export → import → export)
- [ ] CLI commands functional and documented
- [ ] Migration guide written for remaining tools

---

## 11. Future Enhancements

### Phase 6: UI Integration (Post-Launch)

- Visual metadata browser in library UI
- Search interface with filters
- Metadata editing panel
- Batch metadata updates

### Phase 7: Advanced Analytics

- Metadata dashboards (crop quality, transcription completeness)
- Workflow comparison (which workflow produces best results?)
- Quality metrics tracking over time
- Anomaly detection (unusually low confidence, empty transcriptions)

### Phase 8: Metadata Validation

- Schema validation for metadata fields
- Quality checks (e.g., crop box within bounds)
- Automatic correction suggestions
- Metadata completeness reports

---

## 12. Risk Mitigation

### Risk 1: Performance Degradation

**Mitigation:**
- Extensive indexing on query fields
- Benchmark tests before/after
- Caching layer if needed
- Async processing for bulk imports

### Risk 2: Data Loss During Migration

**Mitigation:**
- Backup existing JSONL before import
- Validation tests after import
- Rollback procedure documented
- Dry-run mode for imports

### Risk 3: Tool Migration Complexity

**Mitigation:**
- Start with simple tools (rotate)
- Template/guide for migration
- Backwards compatibility maintained
- Gradual rollout (one tool at a time)

### Risk 4: JSONL Format Divergence

**Mitigation:**
- Round-trip tests ensure consistency
- JSONL format locked (no breaking changes)
- Version metadata in JSONL for future changes

---

## 13. Appendices

### Appendix A: Complete Tool Metadata Schemas

See section 1.2 for examples. Full schemas to be documented per tool during migration.

### Appendix B: Database Size Estimates

**Assumptions:**
- 1000 items per collection
- 6 processing steps per item
- Average 10 metadata fields per step
- Average 100 bytes per metadata entry

**Calculations:**
- `processing_outputs`: 6000 rows × 500 bytes = 3 MB
- `extracted_metadata`: 60,000 rows × 200 bytes = 12 MB
- `step_metadata_versions`: 6000 rows × 1 KB = 6 MB
- **Total per collection: ~21 MB**

For 100 collections: ~2.1 GB (reasonable for SQLite)

### Appendix C: Query Performance Benchmarks

To be established during implementation. Target metrics:
- Simple query (single filter): < 50ms
- Complex query (3+ filters): < 100ms
- Aggregation query: < 200ms
- Full-text search: < 500ms

### Appendix D: Migration Checklist

Per-tool migration checklist:

- [ ] Review current metadata structure
- [ ] Define metadata categories (step_params, step_results, etc.)
- [ ] Add `metadata_api` parameter to tool function
- [ ] Add `processing_context` parameter
- [ ] Restructure metadata dict
- [ ] Call `save_step_metadata()`
- [ ] Test with sample data
- [ ] Verify JSONL backwards compatibility
- [ ] Update workflow executor
- [ ] Integration test with Director
- [ ] Document metadata schema
- [ ] Code review
- [ ] Deploy to production

---

## Conclusion

This architecture provides a solid foundation for unified metadata storage in the Fichero library backend. By centralizing metadata in SQLite while maintaining JSONL compatibility, we enable powerful search and query capabilities without breaking existing workflows. The phased migration approach ensures low risk and allows for iterative improvements.

**Next Steps:**
1. Review and approve this architecture document
2. Create implementation tasks for Phase 1
3. Set up development branch
4. Begin Week 1 implementation

**Questions for Review:**
1. Should JSONL generation be on-demand or real-time?
2. Should we support complex query operators ($gte, $in) in Phase 1 or defer to Phase 5?
3. Should version tracking be full-featured (with rollback) or simple snapshots?
4. Should we add a metadata validation layer before storage?
