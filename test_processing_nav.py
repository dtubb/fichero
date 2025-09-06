#!/usr/bin/env python3
"""
Test script for ProcessingNavigator with real data
"""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, 'src')

from fichero.library.processing_navigator import ProcessingNavigator

def test_processing_navigator():
    """Test the ProcessingNavigator with real data"""
    
    # Test with real data
    test_path = Path('/Volumes/Files/fichero/ernestina_processed/1939-Fabriciano-Mosquera-contra-Compañía-Minera-Chocó-Pacífico')
    
    if not test_path.exists():
        print(f"❌ Test path does not exist: {test_path}")
        return
    
    print(f"🔍 Testing ProcessingNavigator with: {test_path}")
    print()
    
    # Create navigator
    navigator = ProcessingNavigator(test_path)
    
    # Get available steps
    available_steps = navigator.get_available_steps()
    print(f"📋 Available Processing Steps ({len(available_steps)}):")
    for step in available_steps:
        print(f"  ✅ {step.name}: {step.description}")
    print()
    
    # Get processing summary
    summary = navigator.get_processing_summary()
    print(f"📊 Processing Summary:")
    print(f"  Total Files: {summary['total_files']}")
    print(f"  Available Steps: {len(summary['available_steps'])}")
    print()
    
    # Show step details
    print("📁 Step Details:")
    for step_name in summary['available_steps'][:5]:  # Show first 5 steps
        step_info = summary['steps'][step_name]
        print(f"  {step_name}:")
        print(f"    Files: {step_info['file_count']}")
        print(f"    Types: {step_info['file_types']}")
        print(f"    Has Manifest: {step_info['has_manifest']}")
        print()
    
    # Test search
    print("🔍 Search Test:")
    results = navigator.search_across_steps('solicitud')
    print(f"  Search for 'solicitud': {len(results)} results")
    for result in results[:3]:  # Show first 3 results
        print(f"    - {result.step}: {result.name}")
    print()
    
    # Test file content preview
    print("📄 Content Preview Test:")
    transcriptions = navigator.get_step_outputs('transcriptions')
    if transcriptions:
        preview = navigator.get_file_content_preview(transcriptions[0], max_lines=3)
        if preview:
            print(f"  Preview of {transcriptions[0].name}:")
            print(f"    {preview[:200]}..." if len(preview) > 200 else preview)
    print()
    
    # Test manifest reading
    print("📋 Manifest Test:")
    manifest = navigator.get_step_manifest('rotated')
    if manifest:
        print(f"  Rotated step manifest: {manifest['count']} entries")
        print(f"  File: {manifest['file']}")
    else:
        print("  No manifest found for rotated step")
    print()
    
    print("✅ ProcessingNavigator test completed successfully!")

if __name__ == "__main__":
    test_processing_navigator()
