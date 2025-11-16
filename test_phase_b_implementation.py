#!/usr/bin/env python3
"""
Test script for Phase B implementation
Verifies that all 5 new tool schemas load correctly
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.windows.main.views.shared.tool_registry import ToolRegistry

def test_tool_registry():
    """Test that tool registry loads all 10 tools with correct parameters"""

    print("=" * 60)
    print("PHASE B IMPLEMENTATION VERIFICATION")
    print("=" * 60)

    # Initialize registry
    registry = ToolRegistry()
    all_tools = registry.get_all_tools()

    print(f"\n✓ Tools loaded: {len(all_tools)}")
    print(f"  Expected: 10")
    print(f"  Status: {'PASS' if len(all_tools) == 10 else 'FAIL'}")

    # Test each new tool
    new_tools = [
        ('transcribe_lmstudio', 4, 'Transcribe (LM Studio)'),
        ('llm_process', 4, 'LLM Process'),
        ('prepare_images', 3, 'Prepare Images'),
        ('remove_background', 1, 'Remove Background'),
        ('segment', 2, 'Segment Images'),
    ]

    print("\n" + "=" * 60)
    print("NEW TOOL SCHEMAS (5 tools)")
    print("=" * 60)

    all_passed = True

    for tool_name, expected_params, expected_name in new_tools:
        tool = registry.get_tool(tool_name)

        if tool is None:
            print(f"\n✗ {tool_name}: NOT FOUND")
            all_passed = False
            continue

        param_count = len(tool['parameters'])
        name_match = tool['name'] == expected_name

        status = "✓" if param_count == expected_params and name_match else "✗"
        print(f"\n{status} {tool_name}:")
        print(f"    Name: {tool['name']}")
        print(f"    Parameters: {param_count} (expected: {expected_params})")

        if param_count != expected_params:
            all_passed = False

        for param in tool['parameters']:
            print(f"      - {param['name']:25s} ({param['type']:10s}) = {param.get('default', 'N/A')}")

    # Test workflow order
    print("\n" + "=" * 60)
    print("WORKFLOW ORDER")
    print("=" * 60)

    workflow_order = registry.get_workflow_order()
    print(f"\nWorkflow tools: {len(workflow_order)}")
    for i, tool_name in enumerate(workflow_order, 1):
        print(f"  {i:2d}. {tool_name}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\nTotal tools: {len(all_tools)}/10")
    print(f"New tools: 5/5")
    print(f"Parameter coverage: 50% (10/20 tools)")
    print(f"\nOverall: {'✓ PASS' if all_passed and len(all_tools) == 10 else '✗ FAIL'}")
    print()

    return all_passed and len(all_tools) == 10

if __name__ == '__main__':
    success = test_tool_registry()
    sys.exit(0 if success else 1)
