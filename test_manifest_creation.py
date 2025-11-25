"""
Test manifest creation in workflow executor
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_workflow_manifest_creation():
    """Test that WorkflowManifest can be created and written"""
    from fichero.director.workflow_manifest import WorkflowManifest
    import tempfile

    # Create a temporary output directory
    output_path = Path(tempfile.mkdtemp())

    print(f"📁 Testing manifest creation in: {output_path}\n")

    # Create a manifest
    manifest = WorkflowManifest(
        output_path=output_path,
        plan_name="Test Plan",
        workflow_name="default",
        task_id="test-task-123"
    )

    # Simulate workflow execution
    print("⏱️  Simulating workflow execution...\n")

    # Step 1: prepare_images
    manifest.start_step(1, "prepare_images")
    print("   ✓ Started step 1: prepare_images")
    manifest.complete_step(
        step_order=1,
        success=True,
        manifest_path="assets/prepared/prepare_images_manifest.jsonl"
    )
    print("   ✓ Completed step 1: prepare_images\n")

    # Step 2: transcribe_qwen_max
    manifest.start_step(2, "transcribe_qwen_max")
    print("   ✓ Started step 2: transcribe_qwen_max")
    manifest.complete_step(
        step_order=2,
        success=True,
        manifest_path="assets/transcriptions/transcriptions_manifest.jsonl"
    )
    print("   ✓ Completed step 2: transcribe_qwen_max\n")

    # Finalize workflow
    manifest.finalize(success=True)
    print("✅ Finalized workflow manifest\n")

    # Check if file was created
    manifest_file = output_path / "workflow_manifest.json"
    if manifest_file.exists():
        print(f"✅ Workflow manifest created: {manifest_file}\n")

        # Read and display the manifest
        with open(manifest_file, 'r') as f:
            data = json.load(f)

        print("📄 Manifest Contents:")
        print("=" * 60)
        print(f"   Plan: {data['workflow']['plan_name']}")
        print(f"   Workflow: {data['workflow']['workflow_name']}")
        print(f"   Task ID: {data['workflow']['task_id']}")
        print(f"   Success: {data['workflow']['success']}")
        print(f"   Duration: {data['workflow']['duration_seconds']:.2f}s")
        print(f"\n   Steps executed: {len(data['steps'])}")
        for step in data['steps']:
            status_emoji = "✅" if step['status'] == 'success' else "❌"
            print(f"      {status_emoji} Step {step['order']}: {step['name']}")
            if step.get('manifest_file'):
                print(f"         → {step['manifest_file']}")

        # Cleanup
        import shutil
        shutil.rmtree(output_path)
        print(f"\n🧹 Cleaned up temp directory")

        return True
    else:
        print(f"❌ Workflow manifest was not created!")
        return False

if __name__ == "__main__":
    print("🧪 Testing Workflow Manifest Creation\n")
    print("=" * 60)
    print()

    success = test_workflow_manifest_creation()

    print("\n" + "=" * 60)
    if success:
        print("✅ TEST PASSED: Manifest system is working!")
    else:
        print("❌ TEST FAILED: Manifest was not created")
