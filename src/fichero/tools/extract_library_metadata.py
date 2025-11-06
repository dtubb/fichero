import typer
import srsly
from pathlib import Path
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

# Always use absolute imports from fichero.tools.utils
from fichero.tools.utils.files import ensure_dirs, get_relative_path
from fichero.tools.utils.tool_logger import get_tool_logger

tool_logger = get_tool_logger('extract_library_metadata')

def extract_metadata_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    library_db_path: Optional[Path] = None,
    collection_id: Optional[str] = None,
    skip_processing: bool = False,
    **kwargs
) -> Dict[str, int]:
    """
    Extract library metadata for files in the source manifest

    Args:
        source_folder: Source directory containing files
        source_manifest: Input manifest file (JSONL)
        output_folder: Output directory for metadata manifest
        library_db_path: Optional path to library database
        collection_id: Optional collection ID to query
        skip_processing: If True, create placeholder metadata without database query

    Returns:
        Processing statistics dictionary
    """
    # Safely handle paths
    source_folder = Path(os.path.expanduser(str(source_folder))).resolve()
    source_manifest = Path(os.path.expanduser(str(source_manifest))).resolve()
    output_folder = Path(os.path.expanduser(str(output_folder))).resolve()

    tool_logger.progress(f"Extracting library metadata from: {source_manifest}")

    # Output manifest path
    output_manifest = output_folder / "metadata_manifest.jsonl"

    # Ensure output directory exists
    ensure_dirs(output_manifest)

    # Statistics
    stats = {
        "processed_files": 0,
        "metadata_found": 0,
        "metadata_missing": 0,
        "skipped": 0,
        "success": True
    }

    # Check if we're in skip processing mode
    if skip_processing:
        tool_logger.info("Skip processing mode - creating placeholder metadata")
        entries = _create_placeholder_metadata(source_manifest, source_folder)
        stats["skipped"] = len(entries)
        srsly.write_jsonl(output_manifest, entries)
        tool_logger.success(f"Created {len(entries)} placeholder metadata entries in {output_manifest}")
        return stats

    # Validate library context
    if not library_db_path or not collection_id:
        tool_logger.warning("No library database path or collection ID provided - creating empty metadata")
        entries = _create_placeholder_metadata(source_manifest, source_folder)
        stats["metadata_missing"] = len(entries)
        srsly.write_jsonl(output_manifest, entries)
        tool_logger.success(f"Created {len(entries)} empty metadata entries in {output_manifest}")
        return stats

    # Load library storage
    try:
        from fichero.library.storage import LibraryStorage

        library_db_path = Path(library_db_path)
        if not library_db_path.exists():
            tool_logger.warning(f"Library database not found at {library_db_path} - creating empty metadata")
            entries = _create_placeholder_metadata(source_manifest, source_folder)
            stats["metadata_missing"] = len(entries)
            srsly.write_jsonl(output_manifest, entries)
            tool_logger.success(f"Created {len(entries)} empty metadata entries in {output_manifest}")
            return stats

        storage = LibraryStorage(library_db_path)
        tool_logger.info(f"Connected to library database: {library_db_path}")

        # Get all items in collection
        items = storage.get_collection_items(collection_id)
        tool_logger.info(f"Found {len(items)} items in collection {collection_id}")

        # Get collection info
        collection = storage.get_collection(collection_id)
        collection_name = collection.name if collection else "Unknown Collection"
        tool_logger.info(f"Collection: {collection_name}")

        # Build lookup map: source_path -> item
        item_lookup = {}
        for item in items:
            # Try both source_path and local_path as keys
            if item.source_path:
                # Normalize paths for matching
                normalized_source = str(Path(item.source_path).resolve())
                item_lookup[normalized_source] = item

                # Also try without resolving (for relative paths)
                item_lookup[str(item.source_path)] = item

            if item.local_path:
                normalized_local = str(Path(item.local_path).resolve())
                item_lookup[normalized_local] = item

                # Also try without resolving
                item_lookup[str(item.local_path)] = item

        tool_logger.debug(f"Built lookup map with {len(item_lookup)} path variations")

    except Exception as e:
        tool_logger.error(f"Failed to load library storage: {e}")
        tool_logger.warning("Creating empty metadata entries")
        entries = _create_placeholder_metadata(source_manifest, source_folder)
        stats["metadata_missing"] = len(entries)
        stats["success"] = False
        srsly.write_jsonl(output_manifest, entries)
        return stats

    # Read source manifest
    if not source_manifest.exists():
        tool_logger.error(f"Source manifest not found: {source_manifest}")
        stats["success"] = False
        return stats

    try:
        source_entries = list(srsly.read_jsonl(source_manifest))
        tool_logger.info(f"Loaded {len(source_entries)} entries from source manifest")
    except Exception as e:
        tool_logger.error(f"Failed to read source manifest: {e}")
        stats["success"] = False
        return stats

    # Process each entry
    output_entries = []

    for entry in source_entries:
        # Get source file path from entry
        source_file = entry.get('source')
        if not source_file:
            tool_logger.warning(f"Entry missing 'source' field: {entry}")
            continue

        # Try to find matching library item
        library_item = None

        # Try various path matching strategies
        source_path = source_folder / source_file

        # Strategy 1: Try absolute path
        abs_path = str(source_path.resolve())
        if abs_path in item_lookup:
            library_item = item_lookup[abs_path]
            tool_logger.debug(f"Matched by absolute path: {source_file}")

        # Strategy 2: Try relative path
        if not library_item and str(source_file) in item_lookup:
            library_item = item_lookup[str(source_file)]
            tool_logger.debug(f"Matched by relative path: {source_file}")

        # Strategy 3: Try filename matching (fallback)
        if not library_item:
            filename = Path(source_file).name
            for path_key, item in item_lookup.items():
                if Path(path_key).name == filename:
                    library_item = item
                    tool_logger.debug(f"Matched by filename: {source_file}")
                    break

        # Create metadata entry
        metadata_entry = {
            "source": source_file,
            "processed_at": datetime.now().isoformat()
        }

        if library_item:
            # Found matching item - extract full metadata
            metadata_entry["library_metadata"] = {
                "item_id": library_item.id,
                "item_name": library_item.name,
                "collection_id": library_item.collection_id,
                "collection_name": collection_name,
                "created_at": library_item.created_at.isoformat(),
                "updated_at": library_item.updated_at.isoformat(),
                "storage_type": library_item.storage_type,
                "source_path": library_item.source_path,
                "local_path": library_item.local_path,
                "status": library_item.status,
                "type": library_item.type,
                "metadata": library_item.metadata if library_item.metadata else {}
            }

            stats["metadata_found"] += 1
            tool_logger.debug(f"Found metadata for: {source_file} -> {library_item.name}")
        else:
            # No matching item found
            metadata_entry["library_metadata"] = {
                "item_id": None,
                "item_name": Path(source_file).name,
                "collection_id": None,
                "collection_name": None,
                "source_path": str(source_path),
                "metadata": {}
            }

            stats["metadata_missing"] += 1
            tool_logger.debug(f"No metadata found for: {source_file}")

        output_entries.append(metadata_entry)
        stats["processed_files"] += 1

    # Write output manifest
    srsly.write_jsonl(output_manifest, output_entries)
    tool_logger.success(f"Saved {len(output_entries)} metadata entries to {output_manifest}")

    # Print summary
    tool_logger.info("Summary:")
    tool_logger.info(f"  - Total files processed: {stats['processed_files']}")
    tool_logger.info(f"  - Metadata found: {stats['metadata_found']}")
    tool_logger.info(f"  - Metadata missing: {stats['metadata_missing']}")

    return stats


def _create_placeholder_metadata(source_manifest: Path, source_folder: Path) -> List[Dict[str, Any]]:
    """Create placeholder metadata entries for skip processing mode"""

    if not source_manifest.exists():
        tool_logger.warning(f"Source manifest not found: {source_manifest}")
        return []

    try:
        source_entries = list(srsly.read_jsonl(source_manifest))
    except Exception as e:
        tool_logger.error(f"Failed to read source manifest: {e}")
        return []

    entries = []
    for entry in source_entries:
        source_file = entry.get('source')
        if not source_file:
            continue

        # Create placeholder entry
        placeholder = {
            "source": source_file,
            "processed_at": datetime.now().isoformat(),
            "library_metadata": {
                "item_id": "placeholder",
                "item_name": Path(source_file).name,
                "collection_id": "placeholder",
                "collection_name": "Placeholder Collection",
                "source_path": str(source_folder / source_file),
                "metadata": {
                    "placeholder": True,
                    "skip_processing": True
                }
            }
        }

        entries.append(placeholder)

    return entries


def extract_library_metadata(
    source_folder: Path = typer.Argument(..., help="Source directory containing files"),
    source_manifest: Path = typer.Argument(..., help="Input manifest file (JSONL)"),
    output_folder: Path = typer.Argument(..., help="Output directory for metadata manifest"),
    library_db_path: Optional[Path] = typer.Option(None, help="Path to library database"),
    collection_id: Optional[str] = typer.Option(None, help="Collection ID to query"),
    skip_processing: bool = typer.Option(False, "--skip-processing", help="Skip database queries, create placeholder metadata")
):
    """
    Extract library metadata for files in a manifest.

    This tool queries the library database to extract metadata for each file
    in the source manifest. The metadata includes item names, collection info,
    and user-defined JSON metadata fields.

    If no library database or collection ID is provided, placeholder metadata
    is created. This allows the tool to work in workflows where library
    integration is optional.

    Example:
        python -m fichero.tools.extract_library_metadata \\
            assets/cleaned \\
            assets/cleaned/cleaned_manifest.jsonl \\
            assets/library_metadata \\
            --library-db-path ~/Library/fichero.db \\
            --collection-id abc123
    """
    return extract_metadata_batch(
        source_folder,
        source_manifest,
        output_folder,
        library_db_path=library_db_path,
        collection_id=collection_id,
        skip_processing=skip_processing
    )


if __name__ == "__main__":
    typer.run(extract_library_metadata)
