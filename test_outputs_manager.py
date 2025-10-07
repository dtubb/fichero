#!/usr/bin/env python3
"""
Test outputs_manager with nested folder structure
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from fichero.library.outputs_manager import OutputsManager

def test_nested_outputs():
    """Test that outputs_manager can find tools in nested folder structure"""

    # Use the actual output path from Tiny Test processing
    output_path = Path("/Users/dtubb/Library/Application Support/ca.tubb.fichero/library/collections/a7eb82ea-137e-44e1-ace7-48b5d1d6e9f9/outputs/Folder__Tiny_Test/2025-10-06/Catalogue/Tiny_Test_4")

    if not output_path.exists():
        print(f"❌ Output path doesn't exist: {output_path}")
        return

    print(f"✅ Output path exists: {output_path}")

    # Initialize outputs manager
    manager = OutputsManager()

    # Load the output folder
    session = manager.load_output_folder(output_path)
    print(f"✅ Loaded output session")

    # List tools
    tools = manager.list_tools(session)
    print(f"\n📊 Found {len(tools)} tools:")

    for tool in tools:
        print(f"\n  Tool: {tool.tool_name}")
        print(f"    Output folder: {tool.output_folder}")
        print(f"    Manifest: {tool.manifest_path.name}")
        print(f"    Files: {len(tool.files)}")

        # Show first few files
        for file_path in tool.files[:3]:
            print(f"      - {file_path.name}")

        if len(tool.files) > 3:
            print(f"      ... and {len(tool.files) - 3} more")

    if len(tools) > 0:
        print(f"\n✅ SUCCESS: Found {len(tools)} tool outputs in nested structure")
    else:
        print(f"\n❌ FAIL: No tools found")

if __name__ == "__main__":
    test_nested_outputs()
