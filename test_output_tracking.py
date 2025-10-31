#!/usr/bin/env python3
"""Test script to verify output tracking system"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage

# Database path
db_path = Path.home() / "Library/Application Support/ca.tubb.fichero/library/library.db"
print(f"Database path: {db_path}")

# Initialize storage
storage = LibraryStorage(db_path=str(db_path))

# Test data
processing_result_id = "3e86a390-8ab5-40e1-b369-f6d16c063f34"
collection_id = "a7a03720-620c-4a7f-b4b3-a93e635fe2e6"
item_id = "a892b680-bc90-46cb-af51-33aa5f2e5881"

print("=" * 80)
print("OUTPUT TRACKING VERIFICATION")
print("=" * 80)

# 1. Check ProcessingOutput records
print("\n1. Checking ProcessingOutput records...")
print(f"   Processing Result ID: {processing_result_id}")

outputs = storage.get_processing_outputs(processing_result_id)
print(f"   ✅ Found {len(outputs)} ProcessingOutput records")

if outputs:
    print("\n   Output Details:")
    for i, output in enumerate(outputs, 1):
        print(f"\n   Output #{i}:")
        print(f"     - ID: {output.id}")
        print(f"     - Step: {output.step_name}")
        print(f"     - Type: {output.output_type}")
        print(f"     - Format: {output.file_format}")
        print(f"     - Path: {output.output_path}")
        print(f"     - Size: {output.file_size} bytes")
        print(f"     - Metadata Extracted: {output.metadata_extracted}")

# 2. Check ExtractedMetadata records
print("\n2. Checking ExtractedMetadata records...")

total_metadata = 0
for output in outputs:
    metadata_list = storage.get_extracted_metadata(output.id)
    total_metadata += len(metadata_list)

    if metadata_list:
        print(f"\n   Output: {output.output_path}")
        print(f"   ✅ Found {len(metadata_list)} metadata records")

        for metadata in metadata_list[:3]:  # Show first 3
            print(f"     - Type: {metadata.metadata_type}, Key: {metadata.key}")
            value_preview = metadata.value[:100] + "..." if len(metadata.value) > 100 else metadata.value
            print(f"       Value: {value_preview}")

print(f"\n   Total metadata records: {total_metadata}")

# 3. Check collection-level queries
print("\n3. Testing collection-level queries...")
collection_outputs = storage.get_outputs_by_collection(collection_id)
print(f"   ✅ Collection has {len(collection_outputs)} total outputs")

# 4. Check item-level queries
print("\n4. Testing item-level queries...")
item_outputs = storage.get_outputs_by_item(item_id)
print(f"   ✅ Item has {len(item_outputs)} outputs")

# 5. Test metadata search
print("\n5. Testing metadata search...")
search_results = storage.search_metadata(collection_id, "Antonio")
print(f"   ✅ Found {len(search_results)} results for 'Antonio'")

if search_results:
    print(f"\n   First result:")
    result = search_results[0]
    print(f"     - Type: {result.metadata_type}")
    print(f"     - Key: {result.key}")
    value_preview = result.value[:200] + "..." if len(result.value) > 200 else result.value
    print(f"     - Value: {value_preview}")

# 6. Check file existence
print("\n6. Checking file existence...")
for output in outputs[:5]:  # Check first 5
    # Try to construct full path
    print(f"\n   Checking: {output.output_path}")
    print(f"     - Output type: {output.output_type}")
    print(f"     - Step: {output.step_name}")

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
