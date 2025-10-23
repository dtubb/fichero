#!/usr/bin/env python3
"""
Test script to verify library can retrieve processing output data
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager
from fichero.library.path_resolver import get_library_path

async def test_get_item_output_data(item_id: str):
    """Test getting output data for a specific item"""
    print(f"Testing library query for item: {item_id}")
    print("=" * 60)

    # Initialize library manager
    library_path = get_library_path()
    print(f"Library path: {library_path}")

    library_manager = LibraryManager(library_path)
    print("✅ Library manager initialized")

    # Get item info
    item = await library_manager.get_item(item_id)
    if not item:
        print(f"❌ Item not found: {item_id}")
        return

    print(f"\n📄 Item: {item.name}")
    print(f"   Type: {item.type}")
    print(f"   Status: {item.status}")
    print(f"   Source: {item.source_path}")

    # Get output data (the method we're testing)
    print("\n📦 Calling get_item_output_data()...")
    try:
        output_data = await library_manager.get_item_output_data(item_id)

        if output_data:
            print("✅ Output data retrieved successfully!")
            print(f"\n  Has outputs: {output_data.get('has_outputs', False)}")
            print(f"  Workflow: {output_data.get('workflow', 'N/A')}")
            print(f"  Processing date: {output_data.get('processing_date', 'N/A')}")
            print(f"  Output root: {output_data.get('output_root', 'N/A')}")

            processing_steps = output_data.get('processing_steps', [])
            print(f"\n  Processing steps: {len(processing_steps)}")

            for i, step in enumerate(processing_steps, 1):
                step_name = step.step_name if hasattr(step, 'step_name') else str(step)
                file_path = step.file_path if hasattr(step, 'file_path') else 'N/A'
                print(f"    {i}. {step_name}")
                print(f"       Path: {file_path}")
        else:
            print("❌ No output data returned")
            print("(Item may not have been processed yet)")

    except Exception as e:
        print(f"❌ Error calling get_item_output_data(): {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Item ID from the user's Inspector output
    item_id = "190cb920-5448-43b5-aa7c-d550d3543ced"

    if len(sys.argv) > 1:
        item_id = sys.argv[1]

    asyncio.run(test_get_item_output_data(item_id))
