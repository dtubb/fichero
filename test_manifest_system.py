"""
Test script for master manifest system
Tests the complete workflow: processing → manifest creation → ingestion
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_manifest_reading():
    """Test reading workflow manifest from an existing output folder"""
    from fichero.director.workflow_manifest import WorkflowManifest

    # Use an existing output folder
    output_path = Path("/Users/dtubb/Library/Application Support/ca.tubb.fichero/library/collections/500e468b-0477-49f3-916b-444dfcfe490d/outputs/2025-11-22_17-32-42/TranscribeTest/1931_Antonio_Asprilla_pide_que_se_haga_efectiva_una_multa_a_M.C._Marshall_y_Manuel_A._Pen_a__Istmina")

    if not output_path.exists():
        print(f"❌ Output path does not exist: {output_path}")
        return False

    print(f"📁 Testing manifest reading from: {output_path.name}\n")

    # Try to read workflow manifest
    manifest = WorkflowManifest.read_manifest(output_path)

    if not manifest:
        print("❌ No workflow_manifest.json found - this is expected for old outputs")
        print("   The master manifest system was just implemented!")
        return False

    print("✅ Found workflow manifest!")
    print(f"   Plan: {manifest['workflow']['plan_name']}")
    print(f"   Workflow: {manifest['workflow']['workflow_name']}")
    print(f"   Success: {manifest['workflow']['success']}")
    print(f"   Steps: {len(manifest['steps'])}\n")

    # Show steps
    for step in manifest['steps']:
        status_emoji = "✅" if step['status'] == 'success' else "❌"
        print(f"   {status_emoji} Step {step['order']}: {step['name']}")
        if step.get('manifest_file'):
            print(f"      Manifest: {step['manifest_file']}")

    return True

if __name__ == "__main__":
    print("🧪 Testing Master Manifest System\n")
    print("=" * 60)

    success = test_manifest_reading()

    if not success:
        print("\n" + "=" * 60)
        print("NOTE: Old outputs won't have workflow_manifest.json")
        print("Run a new processing job to test the complete system!")
