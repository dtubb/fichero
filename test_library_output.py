#!/usr/bin/env python3
"""
Test script to verify library output loading works correctly
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager
from fichero.library.path_resolver import get_library_path

async def test_item_output():
    """Test loading output for a specific item"""
    # Initialize library manager
    library_path = get_library_path()
    manager = LibraryManager(str(library_path / "library.db"))

    # Test item ID from user's session
    item_id = "7e4ec168-9f0b-46a0-a594-1777c7fd3675"

    print(f"\n{'='*80}")
    print(f"Testing item: {item_id}")
    print(f"{'='*80}\n")

    # Get item
    item = await manager.get_item(item_id)
    if not item:
        print(f"❌ Item not found: {item_id}")
        return

    print(f"✅ Found item: {item.name}")
    print(f"   Type: {item.type}")
    print(f"   Storage: {item.storage_type}")
    if hasattr(item, 'local_path') and item.local_path:
        print(f"   Path: {item.local_path}")

    # Get processing history
    history = await manager.get_processing_history(item_id)
    print(f"\n📜 Processing History ({len(history)} runs):")
    for i, result in enumerate(history, 1):
        print(f"\n   Run {i}:")
        print(f"     Status: {result.status}")
        print(f"     Completed: {result.completed_at}")
        if result.metadata and 'plan' in result.metadata:
            print(f"     Plan: {result.metadata.get('plan')}")
        if result.metadata and 'steps' in result.metadata:
            print(f"     Steps: {len(result.metadata['steps'])}")
            for step in result.metadata['steps']:
                print(f"       - {step.get('step_name')}: {step.get('status')}")

    # Get latest processing result (should prefer completed runs)
    latest_result = await manager.get_latest_processing_result(item_id)
    if not latest_result:
        print(f"\n❌ No processing result found")
        return

    print(f"\n🎯 Selected Processing Result:")
    print(f"   Status: {latest_result.status}")
    print(f"   Completed: {latest_result.completed_at}")
    if latest_result.metadata and 'plan' in latest_result.metadata:
        print(f"   Plan: {latest_result.metadata.get('plan')}")

    # Get output data
    output_data = await manager.get_item_output_data(item_id)

    if output_data:
        print(f"\n📤 Output Data:")
        print(f"   Filename: {output_data.get('filename')}")
        print(f"   Type: {output_data.get('type')}")
        print(f"   Output root: {output_data.get('output_root')}")

        processing_steps = output_data.get('processing_steps', [])
        print(f"\n🔧 Processing Steps ({len(processing_steps)}):")
        for step in processing_steps:
            print(f"\n   Step {step.step_number}: {step.step_name}")
            print(f"     File: {step.file_path.name if hasattr(step, 'file_path') else 'N/A'}")
            print(f"     Type: {step.file_type if hasattr(step, 'file_type') else 'N/A'}")
            print(f"     Exists: {step.file_path.exists() if hasattr(step, 'file_path') else 'N/A'}")

            # Test compatibility properties
            if hasattr(step, 'files'):
                print(f"     .files property: {[f.name for f in step.files]}")
            if hasattr(step, 'tool_name'):
                print(f"     .tool_name property: {step.tool_name}")
    else:
        print(f"\n❌ No output data found")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    asyncio.run(test_item_output())
