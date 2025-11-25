#!/usr/bin/env python3
"""
Debug script for metadata extraction issues
"""

import logging
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.metadata_extractors import UniversalExtractor

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def debug_metadata_extraction():
    """Debug the metadata extraction process"""

    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        # Create storage
        storage = LibraryStorage(db_path)
        extractor = UniversalExtractor(storage)

        # Create a test catalogue file
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir)
            catalogue_dir = test_dir / "assets" / "catalogue"
            catalogue_dir.mkdir(parents=True)

            catalogue_file = catalogue_dir / "test_document_catalogue.json"
            catalogue_data = {
                "title": "Test Document",
                "document_type": "Letter",
                "date": "1965-03-15",
                "author": "Test Author",
                "language": "Spanish",
                "description": "Test description"
            }

            import json
            catalogue_file.write_text(json.dumps(catalogue_data, indent=2))

            print(f"Created test file: {catalogue_file}")
            print(f"File exists: {catalogue_file.exists()}")
            print(f"File content: {catalogue_file.read_text()}")

            # Test metadata extraction
            try:
                metadata_list = extractor.extract_from_output(
                    output_path=catalogue_file,
                    output_type="catalogue",
                    collection_id="test-collection",
                    item_id="test-item",
                    processing_output_id="test-output",
                    step_name="catalogue"
                )

                print(f"\nExtracted metadata:")
                print(f"Number of metadata records: {len(metadata_list)}")
                for i, meta in enumerate(metadata_list):
                    print(f"  {i+1}. key={meta.key}, value={meta.value}, schema_type={meta.schema_type}")

            except Exception as e:
                print(f"ERROR during extraction: {e}")
                import traceback
                traceback.print_exc()

    finally:
        # Clean up
        import os
        try:
            os.unlink(db_path)
        except:
            pass

if __name__ == "__main__":
    debug_metadata_extraction()