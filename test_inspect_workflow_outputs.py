"""
Test script to inspect workflow outputs at collection and file level
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import asyncio
import json

async def main():
    print("=" * 80)
    print("WORKFLOW OUTPUT INSPECTION TEST")
    print("=" * 80)

    # The output folder where workflows write their results
    output_folder = Path("/Users/dtubb/Documents/fichero/Tiny Test/1931 Antonio Asprilla pide que se haga efectiva una multa a M.C. Marshall y Manuel A. Peña; Istmina")

    print(f"\n📁 Inspecting workflow outputs in: {output_folder}")
    print(f"   (Looking for assets/ subfolder)")

    # Check if assets folder exists
    assets_folder = output_folder / "assets"
    if not assets_folder.exists():
        print(f"\n❌ Assets folder not found: {assets_folder}")
        return

    print(f"\n✅ Assets folder found: {assets_folder}")

    # === COLLECTION LEVEL ===
    print("\n" + "=" * 80)
    print("COLLECTION LEVEL: List all processing steps")
    print("=" * 80)

    # List all step folders
    step_folders = [d for d in assets_folder.iterdir() if d.is_dir()]
    print(f"\nFound {len(step_folders)} processing steps:")
    for step in sorted(step_folders):
        print(f"  📂 {step.name}/")

        # Count files in each step
        manifest_files = list(step.glob("*_manifest.jsonl"))
        progress_files = list(step.glob("*_progress.jsonl"))
        other_files = [f for f in step.glob("*") if f.is_file() and not f.name.endswith(('manifest.jsonl', 'progress.jsonl'))]

        print(f"     - Manifests: {len(manifest_files)}")
        print(f"     - Progress:  {len(progress_files)}")
        print(f"     - Other:     {len(other_files)}")

    # === FILE LEVEL ===
    print("\n" + "=" * 80)
    print("FILE LEVEL: Examine individual step outputs (JSON)")
    print("=" * 80)

    # Examine each step's manifest and progress files
    for step_folder in sorted(step_folders):
        print(f"\n📋 Step: {step_folder.name}")
        print("-" * 80)

        # Find manifest file
        manifest_files = list(step_folder.glob("*_manifest.jsonl"))
        if manifest_files:
            manifest_file = manifest_files[0]
            print(f"\n   Manifest: {manifest_file.name}")
            print(f"   Location: {manifest_file}")

            # Read and display manifest entries
            try:
                with open(manifest_file, 'r') as f:
                    lines = f.readlines()

                if not lines:
                    print("   ⚠️  Manifest is empty - no files processed")
                else:
                    print(f"   ✅ {len(lines)} entries in manifest\n")

                    # Display first few entries
                    for i, line in enumerate(lines[:3]):
                        if line.strip():
                            entry = json.loads(line)
                            print(f"   Entry {i+1}:")
                            print(f"      Source:  {entry.get('source', 'N/A')}")
                            print(f"      Success: {entry.get('success', 'N/A')}")
                            print(f"      Outputs: {len(entry.get('outputs', []))} files")

                            if 'error' in entry:
                                print(f"      ❌ Error: {entry['error'][:100]}...")

                            if 'details' in entry and entry['details']:
                                print(f"      Details: {json.dumps(entry['details'], indent=10)[:200]}...")
                            print()

                    if len(lines) > 3:
                        print(f"   ... and {len(lines) - 3} more entries")

            except Exception as e:
                print(f"   ❌ Error reading manifest: {e}")

        # Find progress file
        progress_files = list(step_folder.glob("*_progress.jsonl"))
        if progress_files:
            progress_file = progress_files[0]
            print(f"\n   Progress: {progress_file.name}")

            try:
                with open(progress_file, 'r') as f:
                    progress_data = json.loads(f.read())
                    print(f"      Total:     {progress_data.get('total', 0)}")
                    print(f"      Processed: {progress_data.get('processed', 0)}")
                    print(f"      Failed:    {progress_data.get('failed', 0)}")
                    print(f"      Skipped:   {progress_data.get('skipped', 0)}")
            except Exception as e:
                print(f"   ❌ Error reading progress: {e}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"""
To access workflow outputs:

**Collection Level (all steps):**
   Location: {assets_folder}
   Steps:    {', '.join([s.name for s in sorted(step_folders)])}

**File Level (per-step JSON):**
   Each step has a manifest file showing:
   - Which files were processed
   - Success/failure status
   - Output file paths
   - Processing details
   - Error messages (if any)

**Accessing from CLI:**
   python -m fichero library inspect-outputs "{output_folder}"
    """)

if __name__ == "__main__":
    asyncio.run(main())
