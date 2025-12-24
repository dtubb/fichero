"""
Metadata Extractors for Fichero Library

Automatically extracts metadata from Director processing outputs and stores it
in the library with proper schemas, source labels, and versioning.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from fichero.library.models import ExtractedMetadata, StepFile
from fichero.library.storage import LibraryStorage
from fichero.library.metadata_validator import validate_metadata

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Base class for metadata extractors"""

    def __init__(self, storage: LibraryStorage):
        self.storage = storage

    def extract(self,
                output_path: Path,
                collection_id: str,
                item_id: str,
                processing_output_id: str,
                source_label: str) -> List[ExtractedMetadata]:
        """
        Extract metadata from output file

        Args:
            output_path: Path to output file
            collection_id: Collection ID
            item_id: Item ID
            processing_output_id: ProcessingOutput ID
            source_label: Source label (e.g., "ai_qwen", "manual")

        Returns:
            List of ExtractedMetadata objects
        """
        raise NotImplementedError("Subclasses must implement extract()")

    def _get_next_version(self, item_id: str, schema_type: str, source_label: str) -> int:
        """Get next version number for this item/schema/source combination.

        Uses efficient single SQL query via storage.get_max_metadata_version().
        """
        try:
            max_version = self.storage.get_max_metadata_version(
                item_id=item_id,
                schema_type=schema_type,
                source_label=source_label
            )
            return max_version + 1

        except Exception as e:
            logger.error(f"Error getting next version: {e}")
            return 1


class TranscriptionExtractor(MetadataExtractor):
    """Extracts transcription metadata from JSON/JSONL files.

    Now extracts ALL fields from JSON, not just predefined ones.
    This allows AI tools to produce custom fields like named_entities,
    entities, sentiment, etc. that automatically appear in the UI.
    """

    # Known key aliases to normalize
    KEY_ALIASES = {
        "Transcription": "text",
        "Text": "text",
        "Language": "language",
        "Confidence": "confidence",
        "Model": "model",
        "Engine": "model",
    }

    # Fields that should be treated as the main text content
    TEXT_FIELDS = {"text", "transcription"}

    def extract(self, output_path: Path, collection_id: str, item_id: str,
                processing_output_id: str, source_label: str) -> List[ExtractedMetadata]:
        """Extract transcription metadata - ALL fields from JSON."""
        metadata_list = []

        try:
            if not output_path.exists():
                return metadata_list

            # Read transcription file
            content = output_path.read_text(encoding='utf-8')

            # Try JSON first
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Maybe it's plain text
                data = {"text": content}

            # Get version number
            version = self._get_next_version(item_id, "transcription", source_label)

            # Extract the main text content first
            text = data.get("text", "") or data.get("transcription", "") or ""
            if not text and isinstance(content, str) and not content.strip().startswith("{"):
                text = content

            # Build metadata dict with ALL fields dynamically
            metadata_dict = {}

            for key, value in data.items():
                if value is None:
                    continue

                # Normalize key
                normalized_key = self.KEY_ALIASES.get(key, key)
                normalized_key = normalized_key.lower().replace(" ", "_").replace("-", "_")

                # Skip internal fields
                if normalized_key.startswith("_"):
                    continue

                # Handle text field specially - use normalized "text" key
                if normalized_key in self.TEXT_FIELDS:
                    normalized_key = "text"

                metadata_dict[normalized_key] = value

            # Ensure we have text
            if "text" not in metadata_dict and text:
                metadata_dict["text"] = text

            # Add computed word_count if we have text
            if metadata_dict.get("text"):
                text_value = metadata_dict["text"]
                if isinstance(text_value, str):
                    metadata_dict["word_count"] = len(text_value.split())

            # Get confidence for text field
            text_confidence = data.get("confidence")

            # Validate (optional - may fail for dynamic fields)
            try:
                validation = validate_metadata("transcription", metadata_dict)
                if not validation.is_valid:
                    logger.debug(f"Transcription metadata has extra fields: {validation}")
            except Exception:
                pass  # Validation may fail for dynamic fields, that's OK

            # Create metadata records for each field
            for key, value in metadata_dict.items():
                # Convert lists/dicts to JSON string for storage
                if isinstance(value, (list, dict)):
                    value_str = json.dumps(value, ensure_ascii=False)
                else:
                    value_str = str(value)

                meta = ExtractedMetadata(
                    processing_output_id=processing_output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    schema_type="transcription",
                    source_label=source_label,
                    version=version,
                    key=key,
                    value=value_str,
                    confidence=text_confidence if key == "text" else None
                )
                metadata_list.append(meta)

            logger.debug(f"Extracted {len(metadata_list)} transcription fields from {output_path.name}")

        except Exception as e:
            logger.error(f"Failed to extract transcription metadata from {output_path}: {e}")

        return metadata_list


class CatalogueExtractor(MetadataExtractor):
    """Extracts catalogue metadata from JSON files.

    Now extracts ALL fields from JSON, not just predefined ones.
    This allows AI tools to produce custom fields like named_entities,
    people, places, organizations that automatically appear in the UI.

    Handles nested structures by flattening them - if a field contains
    a dict with simple values, those are extracted as separate fields.
    """

    # Known key aliases to normalize (Title -> title, etc.)
    KEY_ALIASES = {
        "Title": "title",
        "Description": "description",
        "Date": "date",
        "Author": "author",
        "Location": "location",
        "Type": "document_type",
        "Language": "language",
        "Subjects": "subjects",
    }

    def extract(self, output_path: Path, collection_id: str, item_id: str,
                processing_output_id: str, source_label: str) -> List[ExtractedMetadata]:
        """Extract catalogue metadata - ALL fields from JSON."""
        metadata_list = []

        try:
            if not output_path.exists():
                return metadata_list

            # Read catalogue JSON
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Get version number
            version = self._get_next_version(item_id, "catalogue", source_label)

            # Extract ALL fields from JSON dynamically, flattening nested dicts
            catalogue_fields = self._flatten_catalogue_data(data)

            # Create metadata records for each field
            for key, value in catalogue_fields.items():
                # Skip empty values (empty lists, empty strings, None)
                if value is None:
                    continue
                if isinstance(value, list) and len(value) == 0:
                    continue
                if isinstance(value, str) and value.strip() == "":
                    continue
                if isinstance(value, dict) and len(value) == 0:
                    continue

                # Convert lists to JSON string for storage
                # Dicts should have been flattened already
                if isinstance(value, list):
                    value_str = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, dict):
                    # Remaining dicts (complex nested) - store as JSON
                    value_str = json.dumps(value, ensure_ascii=False)
                else:
                    value_str = str(value)

                meta = ExtractedMetadata(
                    processing_output_id=processing_output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    schema_type="catalogue",
                    source_label=source_label,
                    version=version,
                    key=key,
                    value=value_str
                )
                metadata_list.append(meta)

            logger.debug(f"Extracted {len(metadata_list)} catalogue fields from {output_path.name}")

        except Exception as e:
            logger.error(f"Failed to extract catalogue metadata from {output_path}: {e}")

        return metadata_list

    def _flatten_catalogue_data(self, data: dict, prefix: str = "") -> dict:
        """
        Flatten catalogue data, extracting nested dict values as separate fields.

        Handles cases like:
        - {"catalogue": {"resumen": "text"}} -> {"resumen": "text"}
        - {"data": {"field1": "val1", "field2": []}} -> {"field1": "val1"}

        Args:
            data: Dict to flatten
            prefix: Key prefix for nested fields (usually empty)

        Returns:
            Flattened dict with normalized keys
        """
        catalogue_fields = {}

        for key, value in data.items():
            if value is None:
                continue

            # Normalize key: apply aliases, then lowercase with underscores
            normalized_key = self.KEY_ALIASES.get(key, key)
            normalized_key = normalized_key.lower().replace(" ", "_").replace("-", "_")

            # Skip internal/system fields
            if normalized_key.startswith("_"):
                continue

            # Add prefix if provided
            full_key = f"{prefix}{normalized_key}" if prefix else normalized_key

            # If value is a dict with simple values, flatten it
            if isinstance(value, dict):
                # Check if this looks like a wrapper dict (single key containing another dict)
                # or a dict of simple values
                has_nested_dict = any(isinstance(v, dict) for v in value.values())
                all_empty = all(
                    v is None or
                    (isinstance(v, list) and len(v) == 0) or
                    (isinstance(v, str) and v.strip() == "") or
                    (isinstance(v, dict) and len(v) == 0)
                    for v in value.values()
                )

                if all_empty:
                    # Skip entirely empty nested objects
                    continue
                elif not has_nested_dict:
                    # Flat dict - extract its values directly
                    nested = self._flatten_catalogue_data(value, "")
                    catalogue_fields.update(nested)
                else:
                    # Complex nested structure - store as JSON
                    catalogue_fields[full_key] = value
            else:
                catalogue_fields[full_key] = value

        return catalogue_fields


class FileInfoExtractor(MetadataExtractor):
    """Extracts file metadata from manifest files"""

    def extract(self, output_path: Path, collection_id: str, item_id: str,
                processing_output_id: str, source_label: str) -> List[ExtractedMetadata]:
        """Extract file info metadata from file or manifest"""
        metadata_list = []

        try:
            if not output_path.exists():
                return metadata_list

            # Get version number
            version = self._get_next_version(item_id, "file_info", source_label)

            # Get file stats
            stats = output_path.stat()

            metadata_dict = {
                "file_path": str(output_path.name),
                "file_size": stats.st_size,
                "format": output_path.suffix.lstrip('.')
            }

            # Try to get image dimensions if it's an image
            if output_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']:
                try:
                    from PIL import Image
                    with Image.open(output_path) as img:
                        metadata_dict["width"] = img.width
                        metadata_dict["height"] = img.height
                        metadata_dict["mime_type"] = f"image/{output_path.suffix.lstrip('.').lower()}"
                except Exception:
                    pass

            # Create metadata records
            for key, value in metadata_dict.items():
                meta = ExtractedMetadata(
                    processing_output_id=processing_output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    schema_type="file_info",
                    source_label=source_label,
                    version=version,
                    key=key,
                    value=str(value)
                )
                metadata_list.append(meta)

        except Exception as e:
            logger.error(f"Failed to extract file info metadata from {output_path}: {e}")

        return metadata_list


class ManifestExtractor(MetadataExtractor):
    """Extracts metadata from JSONL manifest files"""

    def extract(self, manifest_path: Path, collection_id: str, item_id: str,
                processing_output_id: str, source_label: str) -> List[ExtractedMetadata]:
        """Extract step results from manifest file"""
        metadata_list = []

        try:
            if not manifest_path.exists():
                return metadata_list

            # Read manifest
            with open(manifest_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Get version number
                        version = self._get_next_version(item_id, "step_result", source_label)

                        # Extract step result metadata
                        metadata_dict = {
                            "tool_name": entry.get("tool") or entry.get("step"),
                            "status": entry.get("status", "success"),
                            "processing_time": entry.get("processing_time"),
                        }

                        # Add error message if failed
                        if entry.get("error"):
                            metadata_dict["error_message"] = entry["error"]

                        # Create metadata records
                        for key, value in metadata_dict.items():
                            if value is not None:
                                meta = ExtractedMetadata(
                                    processing_output_id=processing_output_id,
                                    collection_id=collection_id,
                                    item_id=item_id,
                                    schema_type="step_result",
                                    source_label=source_label,
                                    version=version,
                                    key=key,
                                    value=str(value)
                                )
                                metadata_list.append(meta)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Failed to extract manifest metadata from {manifest_path}: {e}")

        return metadata_list


class UniversalExtractor:
    """Orchestrates all metadata extractors based on file type"""

    def __init__(self, storage: LibraryStorage):
        self.storage = storage
        self.extractors = {
            "transcription": TranscriptionExtractor(storage),
            "catalogue": CatalogueExtractor(storage),
            "file_info": FileInfoExtractor(storage),
            "manifest": ManifestExtractor(storage),
        }

    def extract_from_output(self,
                           output_path: Path,
                           output_type: str,
                           collection_id: str,
                           item_id: Optional[str],
                           processing_output_id: str,
                           step_name: str,
                           workflow_manifest: Optional[Dict] = None,
                           model_name: Optional[str] = None,
                           provider_name: Optional[str] = None) -> List[ExtractedMetadata]:
        """
        Extract metadata from processing output

        Args:
            output_path: Path to output file
            output_type: Type of output (transcription, catalogue, etc.)
            collection_id: Collection ID
            item_id: Item ID (None for collection-level outputs)
            processing_output_id: ProcessingOutput ID
            step_name: Step name (used as source_label)
            workflow_manifest: Workflow manifest with scope information
            model_name: Model used for this output (e.g., "qwen-vl-ocr")
            provider_name: Provider used (e.g., "dashscope")

        Returns:
            List of extracted metadata records
        """
        metadata_list = []

        try:
            # Determine if this should be collection-level metadata using workflow manifest scope
            is_collection_level = self._is_collection_level_output(step_name, output_type, output_path, item_id, workflow_manifest)

            # Distinguish between true collection-level and folder-level metadata
            # Folder-level metadata (like catalogue_folder) should keep item_id but be marked as collection_level
            is_folder_level = is_collection_level and item_id and any(pattern in step_name.lower() for pattern in ["folder", "directory"])

            # For true collection-level metadata (no item_id), set item_id to None
            # For folder-level metadata, keep the folder's item_id
            if is_collection_level and not is_folder_level:
                effective_item_id = None
            else:
                effective_item_id = item_id

            # Determine source label from step name and output type
            source_label = self._determine_source_label(step_name, output_type, output_path)

            # Select appropriate extractor
            if output_type == "transcription":
                extractor = self.extractors["transcription"]
                metadata_list = extractor.extract(
                    output_path, collection_id, effective_item_id,
                    processing_output_id, source_label
                )
            elif output_type == "catalogue":
                # Defensive check: catalogue extractor only works with JSON files
                if output_path.suffix.lower() not in ['.json', '.jsonl']:
                    logger.warning(f"[METADATA] Skipping non-JSON file marked as catalogue: {output_path.name} (suffix: {output_path.suffix})")
                else:
                    extractor = self.extractors["catalogue"]
                    metadata_list = extractor.extract(
                        output_path, collection_id, effective_item_id,
                        processing_output_id, source_label
                    )
            elif output_type in ["prepared_image", "enhanced_image", "image"]:
                extractor = self.extractors["file_info"]
                metadata_list = extractor.extract(
                    output_path, collection_id, effective_item_id,
                    processing_output_id, source_label
                )
            elif output_path.suffix == ".jsonl" and "manifest" in output_path.name:
                extractor = self.extractors["manifest"]
                metadata_list = extractor.extract(
                    output_path, collection_id, effective_item_id,
                    processing_output_id, source_label
                )
            elif output_type == "json_data":
                # Handle json_data by detecting what type it actually is
                path_str = str(output_path).lower()
                if any(keyword in path_str for keyword in ['catalogue', 'catalog']) or \
                   any(keyword in output_path.name.lower() for keyword in ['catalogue', 'catalog']):
                    # Route catalogue files to catalogue extractor
                    extractor = self.extractors["catalogue"]
                    metadata_list = extractor.extract(
                        output_path, collection_id, effective_item_id,
                        processing_output_id, source_label
                    )

            # Store metadata in database and index for search
            for metadata in metadata_list:
                # Set the collection_level flag based on our detection
                metadata.collection_level = is_collection_level
                # Set model/provider info for version tracking
                metadata.model_name = model_name
                metadata.provider_name = provider_name
                metadata.edited_by = "ai" if model_name else None  # Mark as AI-generated if model is known
                success = self.storage.add_extracted_metadata(metadata)
                if success:
                    # Index searchable content (transcriptions, catalogues)
                    if metadata.schema_type in ["transcription", "catalogue", "translation"]:
                        self.storage.index_metadata_for_search(metadata)
                    logger.debug(f"Extracted and stored metadata: {metadata.schema_type}.{metadata.key}")

        except Exception as e:
            logger.error(f"Failed to extract metadata from {output_path}: {e}")

        return metadata_list

    def _determine_source_label(self, step_name: str, output_type: str, output_path: Path) -> str:
        """Determine source label from step name and context"""

        # Extract model/engine from filename or step name
        filename = output_path.stem.lower()
        step_lower = step_name.lower()

        # Check for specific models/engines
        if "qwen" in filename or "qwen" in step_lower:
            return "ai_qwen"
        elif "gpt" in filename or "openai" in step_lower:
            return "ai_gpt"
        elif "claude" in filename or "claude" in step_lower:
            return "ai_claude"
        elif "lmstudio" in filename or "lmstudio" in step_lower:
            return "ai_lmstudio"
        elif "manual" in filename or "human" in filename:
            return "human_corrected"
        elif "yolo" in filename or "yolo" in step_lower:
            return "yolo_v8"
        elif "paddleocr" in filename or "paddle" in step_lower:
            return "paddleocr"

        # Default: use step name as source
        return step_name.lower().replace("_", "-")

    def _is_collection_level_output(self, step_name: str, output_type: str, output_path: Path,
                                    item_id: Optional[str], workflow_manifest: Optional[Dict] = None) -> bool:
        """
        Determine if an output should be treated as collection-level metadata

        Uses the workflow manifest's output_scope information when available:
        - "leaf": File-level outputs (item-specific metadata)
        - "node": Collection-level outputs (applies to entire collection)
        - "intermediate": Processing outputs (typically not displayed in UI)

        Falls back to heuristic detection when manifest data unavailable.

        Args:
            step_name: Step name from processing
            output_type: Type of output (transcription, catalogue, etc.)
            output_path: Path to output file
            item_id: Item ID (may indicate file-level processing)
            workflow_manifest: Workflow manifest containing scope information

        Returns:
            True if output should be collection-level, False for file-level
        """
        # First, check workflow manifest for explicit scope information
        if workflow_manifest and 'steps' in workflow_manifest:
            for step in workflow_manifest['steps']:
                if step.get('name') == step_name and 'output_scope' in step:
                    output_scope = step['output_scope']
                    if output_scope == 'node':
                        logger.debug(f"[SCOPE] Step '{step_name}' marked as 'node' scope - collection-level metadata")
                        return True
                    elif output_scope == 'leaf':
                        logger.debug(f"[SCOPE] Step '{step_name}' marked as 'leaf' scope - file-level metadata")
                        return False
                    elif output_scope == 'intermediate':
                        logger.debug(f"[SCOPE] Step '{step_name}' marked as 'intermediate' scope - processing-only")
                        # For intermediate outputs, treat as collection-level if no item_id, otherwise file-level
                        return item_id is None
                    break

        # Fallback to heuristic detection if no manifest scope information
        step_lower = step_name.lower()
        filename = output_path.name.lower()
        output_type_lower = output_type.lower()

        # Collection-level indicators in step names
        collection_step_patterns = [
            "catalogue_folder",
            "collection_summary",
            "batch_process",
            "folder_summary",
            "aggregate_",
            "batch_",
            "collection_",
            "folder_"
        ]

        # Collection-level indicators in output types
        collection_output_types = [
            "collection_catalogue",
            "folder_catalogue",
            "batch_summary",
            "collection_summary"
        ]

        # Collection-level indicators in file paths
        # These patterns should be more specific to avoid false positives
        collection_path_patterns = [
            "collection_summary",
            "folder_summary",
            "batch_summary",
            "collection_catalogue",
            "folder_catalogue"
        ]

        # IMPORTANT: If we have a valid item_id, this is likely file-level metadata
        # Only override this for explicit collection-level indicators
        has_valid_item_id = item_id and item_id.strip() and item_id != "None"

        # Check step name patterns (highest priority - explicit collection-level indicators)
        for pattern in collection_step_patterns:
            if pattern in step_lower:
                return True

        # Check output type
        if output_type_lower in collection_output_types:
            return True

        # Check if output is in a collection-level directory
        # Only look at the path relative to the outputs directory to avoid false positives
        # from the library storage path (e.g., .../library/collections/...)
        try:
            # Find the outputs directory in the path and only check parts after it
            path_parts = list(output_path.parts)
            output_relative_parts = []

            # Look for 'outputs' or 'assets' directory to establish the relative path
            for i, part in enumerate(path_parts):
                if part.lower() in ['outputs', 'assets']:
                    # Take everything after this directory
                    output_relative_parts = [p.lower() for p in path_parts[i+1:]]
                    break

            # If no outputs/assets found, just use the last few parts of the path
            if not output_relative_parts:
                output_relative_parts = [p.lower() for p in path_parts[-3:]]  # Last 3 parts only

            # Now check for collection patterns in the relative path only
            # But only if we don't have a valid item_id (which indicates file-level)
            if not has_valid_item_id:
                for pattern in collection_path_patterns:
                    if any(pattern in part for part in output_relative_parts):
                        return True

        except Exception:
            # Fallback to original behavior if path parsing fails
            # But only if we don't have a valid item_id
            if not has_valid_item_id:
                path_parts = [part.lower() for part in output_path.parts[-3:]]  # Only last 3 parts
                for pattern in collection_path_patterns:
                    if any(pattern in part for part in path_parts):
                        return True

        # Special case: catalogue outputs are typically collection-level
        if output_type_lower == "catalogue" and not item_id:
            return True

        # Special case: if item_id is None or empty, it's likely collection-level
        if not item_id or item_id.strip() == "":
            return True

        # Default: file-level metadata
        return False
