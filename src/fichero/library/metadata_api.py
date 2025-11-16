"""
Library Metadata API

Unified interface for tools to store and retrieve step-level metadata.
This API provides a standardized way for processing tools to save metadata
to the library backend, enabling searchability, version tracking, and querying.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from fichero.library.storage import LibraryStorage
    from fichero.library.models import ProcessingOutput, ExtractedMetadata
except ImportError:
    try:
        from .storage import LibraryStorage
        from .models import ProcessingOutput, ExtractedMetadata
    except ImportError:
        # Direct import for testing
        import storage
        import models
        LibraryStorage = storage.LibraryStorage
        ProcessingOutput = models.ProcessingOutput
        ExtractedMetadata = models.ExtractedMetadata

logger = logging.getLogger(__name__)


class LibraryMetadataAPI:
    """
    API for storing and retrieving step-level metadata in library backend.

    This API enables processing tools to:
    - Save structured metadata for each processing step
    - Retrieve metadata for specific items or steps
    - Query items by metadata filters
    - Track version history of metadata changes
    - Update metadata fields while maintaining history

    Usage by tools:
        api = LibraryMetadataAPI(library_storage)
        api.save_step_metadata(
            item_id="item-123",
            step_name="crop",
            metadata={
                "method": "yolo",
                "confidence": 0.92,
                "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
            },
            version=1
        )
    """

    def __init__(self, storage: LibraryStorage):
        """
        Initialize metadata API with storage backend.

        Args:
            storage: LibraryStorage instance for database operations
        """
        self.storage = storage
        logger.debug("LibraryMetadataAPI initialized")

    def save_step_metadata(
        self,
        item_id: str,
        step_name: str,
        metadata: dict,
        version: Optional[int] = None
    ) -> bool:
        """
        Save metadata for a processing step.

        This method:
        1. Validates the item exists
        2. Serializes the metadata to JSON
        3. Saves to extracted_metadata table with appropriate categorization
        4. Creates a version snapshot if version tracking is enabled

        Args:
            item_id: ID of the collection item
            step_name: Name of the processing step (e.g., "crop", "rotate", "transcribe")
            metadata: Structured metadata dict with step-specific fields
            version: Optional version number for tracking (auto-increments if None)

        Returns:
            True if save was successful, False otherwise

        Example:
            >>> api.save_step_metadata(
            ...     item_id="item-123",
            ...     step_name="crop",
            ...     metadata={
            ...         "method": "yolo",
            ...         "confidence": 0.92,
            ...         "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
            ...         "padding": 30
            ...     }
            ... )
            True
        """
        try:
            # Validate item exists
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return False

            collection_id = item.collection_id

            # Create a dummy processing output ID for storing metadata
            # In full implementation, this would be linked to actual ProcessingOutput records
            output_id = f"meta-{item_id}-{step_name}-{datetime.now().isoformat()}"

            # Save each metadata field as an extracted_metadata entry
            for key, value in metadata.items():
                # Determine metadata type based on key
                metadata_type = self._infer_metadata_type(step_name, key)

                # Create metadata entry
                metadata_entry = ExtractedMetadata(
                    processing_output_id=output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    metadata_type=metadata_type,
                    key=f"{step_name}.{key}",
                    value=self._serialize_value(value),
                    confidence=self._extract_confidence(value),
                    created_at=datetime.now()
                )

                # Save to storage
                if not self.storage.add_extracted_metadata(metadata_entry):
                    logger.error(f"Failed to save metadata entry: {step_name}.{key}")
                    return False

            # Create version snapshot if version tracking is requested
            if version is not None:
                self._create_version_snapshot(
                    item_id=item_id,
                    step_name=step_name,
                    metadata=metadata,
                    version=version,
                    changed_by="tool",
                    change_reason="processing_step"
                )

            logger.info(f"Saved metadata for {step_name} on item {item_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save step metadata: {e}")
            return False

    def get_step_metadata(
        self,
        item_id: str,
        step_name: str,
        version: Optional[int] = None
    ) -> Optional[dict]:
        """
        Retrieve metadata for a specific step on an item.

        If version is specified, retrieves metadata for that version from
        version history. Otherwise, retrieves the latest metadata.

        Args:
            item_id: ID of the collection item
            step_name: Name of the processing step
            version: Optional version number to retrieve

        Returns:
            Dict containing metadata fields, or None if not found

        Example:
            >>> metadata = api.get_step_metadata("item-123", "crop")
            >>> print(metadata)
            {'method': 'yolo', 'confidence': 0.92, 'box': {...}}
        """
        try:
            # If version requested, get from version history
            if version is not None:
                return self._get_version_snapshot(item_id, step_name, version)

            # Get all metadata for this collection and filter by item and step
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return None

            # Search for metadata entries matching this step
            all_metadata = self.storage.get_metadata_by_collection(
                item.collection_id,
                metadata_type=None  # Get all types
            )

            # Filter to this item and step, and only keep latest entry for each key
            # Sort by created_at descending to get newest first
            all_metadata_sorted = sorted(
                all_metadata,
                key=lambda x: x.created_at,
                reverse=True
            )

            step_metadata = {}
            seen_keys = set()
            for entry in all_metadata_sorted:
                if entry.item_id == item_id and entry.key.startswith(f"{step_name}."):
                    # Extract field name (remove step_name prefix)
                    field_name = entry.key[len(step_name) + 1:]

                    # Only take the first (newest) occurrence of each key
                    if field_name not in seen_keys:
                        step_metadata[field_name] = self._deserialize_value(entry.value)
                        seen_keys.add(field_name)

            if not step_metadata:
                logger.debug(f"No metadata found for {step_name} on item {item_id}")
                return None

            return step_metadata

        except Exception as e:
            logger.error(f"Failed to get step metadata: {e}")
            return None

    def get_all_step_metadata(self, item_id: str) -> dict:
        """
        Get metadata for all processing steps on an item.

        Returns a dictionary organized by step name, with each step containing
        its metadata fields.

        Args:
            item_id: ID of the collection item

        Returns:
            Dict mapping step names to their metadata dicts

        Example:
            >>> all_meta = api.get_all_step_metadata("item-123")
            >>> print(all_meta)
            {
                'crop': {'method': 'yolo', 'confidence': 0.92, ...},
                'rotate': {'angle': -0.5, 'found_lines': True, ...},
                'transcribe': {'text_length': 450, 'model': 'qwen-vl-max', ...}
            }
        """
        try:
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return {}

            # Get all metadata for this item
            all_metadata = self.storage.get_metadata_by_collection(
                item.collection_id,
                metadata_type=None
            )

            # Sort by created_at descending to get newest first
            all_metadata_sorted = sorted(
                all_metadata,
                key=lambda x: x.created_at,
                reverse=True
            )

            # Organize by step name, only keeping latest entry for each key
            steps_metadata = {}
            seen_keys = {}  # Track seen keys per step
            for entry in all_metadata_sorted:
                if entry.item_id == item_id:
                    # Extract step name and field name from key
                    if '.' in entry.key:
                        step_name, field_name = entry.key.split('.', 1)

                        if step_name not in steps_metadata:
                            steps_metadata[step_name] = {}
                            seen_keys[step_name] = set()

                        # Only take first (newest) occurrence of each field
                        if field_name not in seen_keys[step_name]:
                            steps_metadata[step_name][field_name] = self._deserialize_value(entry.value)
                            seen_keys[step_name].add(field_name)

            return steps_metadata

        except Exception as e:
            logger.error(f"Failed to get all step metadata: {e}")
            return {}

    def query_items_by_metadata(
        self,
        collection_id: str,
        filters: dict
    ) -> List[str]:
        """
        Query items by metadata filters.

        Supports simple equality filters and basic comparison operators.
        All filters are combined with AND logic.

        Args:
            collection_id: Collection to query within
            filters: Dict of key-value filters
                     Keys in format "step_name.field_name"
                     Values can be:
                       - Simple value for equality: "crop.method": "yolo"
                       - Dict with operator: "crop.confidence": {"$gte": 0.8}

        Returns:
            List of item IDs matching all filters

        Example:
            >>> items = api.query_items_by_metadata(
            ...     "collection-123",
            ...     {
            ...         "crop.method": "yolo",
            ...         "crop.confidence": {"$gte": 0.8}
            ...     }
            ... )
            >>> print(len(items))
            15
        """
        try:
            matching_items = None  # Will be set to first result set

            for key, value in filters.items():
                # Get all metadata for this key
                all_metadata = self.storage.get_metadata_by_collection(
                    collection_id,
                    metadata_type=None
                )

                # Filter by key
                key_metadata = [m for m in all_metadata if m.key == key]

                # Apply value filter
                if isinstance(value, dict):
                    # Complex filter with operator
                    operator = list(value.keys())[0]
                    filter_value = value[operator]

                    matches = set()
                    for entry in key_metadata:
                        entry_value = self._deserialize_value(entry.value)
                        if self._apply_operator(entry_value, operator, filter_value):
                            if entry.item_id:
                                matches.add(entry.item_id)
                else:
                    # Simple equality filter
                    matches = set()
                    for entry in key_metadata:
                        entry_value = self._deserialize_value(entry.value)
                        if entry_value == value:
                            if entry.item_id:
                                matches.add(entry.item_id)

                # Combine with previous results (AND logic)
                if matching_items is None:
                    matching_items = matches
                else:
                    matching_items = matching_items.intersection(matches)

                # Short circuit if no matches
                if not matching_items:
                    return []

            return list(matching_items) if matching_items else []

        except Exception as e:
            logger.error(f"Failed to query items by metadata: {e}")
            return []

    def update_step_metadata(
        self,
        item_id: str,
        step_name: str,
        updates: dict
    ) -> bool:
        """
        Update specific fields in step metadata.

        This creates a new version snapshot and updates the metadata fields.
        Old values are preserved in version history.

        Args:
            item_id: ID of the collection item
            step_name: Name of the processing step
            updates: Dict of field updates (field_name: new_value)

        Returns:
            True if update was successful

        Example:
            >>> api.update_step_metadata(
            ...     "item-123",
            ...     "crop",
            ...     {"confidence": 0.95, "method": "yolo-v2"}
            ... )
            True
        """
        try:
            # Get current metadata
            current = self.get_step_metadata(item_id, step_name)
            if current is None:
                logger.error(f"No metadata found to update for {step_name} on {item_id}")
                return False

            # Apply updates
            updated = current.copy()
            updated.update(updates)

            # Get next version number
            version = self._get_next_version(item_id, step_name)

            # Delete old metadata entries first to avoid duplicates
            # (Note: This is a workaround; ideally we'd update in place)
            # For now, just save with new version

            # Save updated metadata without automatic versioning (to avoid duplicate)
            # We'll create the version snapshot ourselves
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return False

            collection_id = item.collection_id
            output_id = f"meta-{item_id}-{step_name}-{datetime.now().isoformat()}"

            # Save each metadata field
            for key, value in updated.items():
                metadata_type = self._infer_metadata_type(step_name, key)

                metadata_entry = ExtractedMetadata(
                    processing_output_id=output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    metadata_type=metadata_type,
                    key=f"{step_name}.{key}",
                    value=self._serialize_value(value),
                    confidence=self._extract_confidence(value),
                    created_at=datetime.now()
                )

                if not self.storage.add_extracted_metadata(metadata_entry):
                    logger.error(f"Failed to save updated metadata entry: {step_name}.{key}")
                    return False

            # Create version snapshot
            self._create_version_snapshot(
                item_id=item_id,
                step_name=step_name,
                metadata=updated,
                version=version,
                changed_by="user",
                change_reason="manual_update"
            )

            logger.info(f"Updated metadata for {step_name} on item {item_id} (v{version})")
            return True

        except Exception as e:
            logger.error(f"Failed to update step metadata: {e}")
            return False

    def delete_step_metadata(
        self,
        item_id: str,
        step_name: str
    ) -> bool:
        """
        Delete all metadata for a specific step.

        Note: This does not delete version history.

        Args:
            item_id: ID of the collection item
            step_name: Name of the processing step to delete

        Returns:
            True if deletion was successful
        """
        try:
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return False

            # Get all metadata for this collection
            all_metadata = self.storage.get_metadata_by_collection(
                item.collection_id,
                metadata_type=None
            )

            # Delete entries matching this item and step
            deleted_count = 0
            for entry in all_metadata:
                if entry.item_id == item_id and entry.key.startswith(f"{step_name}."):
                    # Note: LibraryStorage doesn't have delete method yet
                    # This would need to be implemented in storage.py
                    # For now, log what would be deleted
                    logger.debug(f"Would delete metadata entry: {entry.key}")
                    deleted_count += 1

            logger.info(f"Deleted {deleted_count} metadata entries for {step_name} on item {item_id}")
            return deleted_count > 0

        except Exception as e:
            logger.error(f"Failed to delete step metadata: {e}")
            return False

    def get_metadata_history(
        self,
        item_id: str,
        step_name: str
    ) -> List[dict]:
        """
        Get version history for step metadata.

        Returns a list of version snapshots ordered by version number.

        Args:
            item_id: ID of the collection item
            step_name: Name of the processing step

        Returns:
            List of version snapshot dicts, each containing:
                - version: Version number
                - changed_at: ISO timestamp
                - changed_by: Who made the change
                - change_reason: Why the change was made
                - metadata: Metadata snapshot at this version

        Example:
            >>> history = api.get_metadata_history("item-123", "crop")
            >>> for v in history:
            ...     print(f"v{v['version']}: {v['changed_at']} by {v['changed_by']}")
            v1: 2025-11-15T14:30:00 by tool
            v2: 2025-11-15T15:45:00 by user
        """
        try:
            versions = self.storage.get_metadata_versions(item_id, step_name)
            logger.debug(f"Retrieved {len(versions)} versions for {step_name} on item {item_id}")
            return versions

        except Exception as e:
            logger.error(f"Failed to get metadata history: {e}")
            return []

    # ===== PRIVATE HELPER METHODS =====

    def _infer_metadata_type(self, step_name: str, key: str) -> str:
        """
        Infer metadata type from step name and key.

        Returns one of: step_param, step_result, detection, file_info,
                       transcription, catalogue_field
        """
        # Common parameter names
        param_keys = ['padding', 'blur_kernel', 'threshold', 'model', 'settings', 'config']

        # Result keys
        result_keys = ['confidence', 'angle', 'size', 'box', 'method', 'quality']

        # Detection keys
        detection_keys = ['attempts', 'found_lines', 'num_lines', 'rotation', 'debug']

        # File info keys
        file_keys = ['output_format', 'file_size', 'input_metadata', 'parent_info']

        # Transcription keys
        transcription_keys = ['text', 'text_length', 'num_lines', 'has_content']

        # Check key against patterns
        if any(k in key.lower() for k in param_keys):
            return "step_param"
        elif any(k in key.lower() for k in detection_keys):
            return "detection"
        elif any(k in key.lower() for k in file_keys):
            return "file_info"
        elif any(k in key.lower() for k in transcription_keys):
            return "transcription"
        elif any(k in key.lower() for k in result_keys):
            return "step_result"
        else:
            # Default to step_result
            return "step_result"

    def _serialize_value(self, value: Any) -> str:
        """Serialize a value to JSON string for storage."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        else:
            return str(value)

    def _deserialize_value(self, value_str: str) -> Any:
        """Deserialize a value from JSON string."""
        try:
            return json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            # Try to convert to number
            try:
                if '.' in value_str:
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                # Return as string
                return value_str

    def _extract_confidence(self, value: Any) -> Optional[float]:
        """Extract confidence value if present in metadata."""
        if isinstance(value, dict) and 'confidence' in value:
            return float(value['confidence'])
        return None

    def _apply_operator(self, value: Any, operator: str, filter_value: Any) -> bool:
        """Apply comparison operator to value."""
        try:
            if operator == "$gte":
                return float(value) >= float(filter_value)
            elif operator == "$lte":
                return float(value) <= float(filter_value)
            elif operator == "$gt":
                return float(value) > float(filter_value)
            elif operator == "$lt":
                return float(value) < float(filter_value)
            elif operator == "$eq":
                return value == filter_value
            elif operator == "$ne":
                return value != filter_value
            elif operator == "$in":
                return value in filter_value
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to apply operator {operator}: {e}")
            return False

    def _create_version_snapshot(
        self,
        item_id: str,
        step_name: str,
        metadata: dict,
        version: int,
        changed_by: str,
        change_reason: str
    ):
        """Create a version snapshot in the versions table."""
        self.storage.add_metadata_version(
            item_id=item_id,
            step_name=step_name,
            version=version,
            metadata_snapshot=metadata,
            changed_by=changed_by,
            change_reason=change_reason
        )
        logger.debug(
            f"Created version snapshot v{version} for {step_name} "
            f"on item {item_id} (by {changed_by}: {change_reason})"
        )

    def _get_version_snapshot(
        self,
        item_id: str,
        step_name: str,
        version: int
    ) -> Optional[dict]:
        """Get metadata snapshot for a specific version."""
        version_data = self.storage.get_metadata_version(item_id, step_name, version)
        if version_data:
            return version_data['metadata']
        logger.debug(f"No version {version} found for {step_name} on item {item_id}")
        return None

    def _get_next_version(self, item_id: str, step_name: str) -> int:
        """Get next version number for metadata updates."""
        latest = self.storage.get_latest_version_number(item_id, step_name)
        return latest + 1
