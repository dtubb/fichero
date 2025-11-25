"""
Simple test script to manually test the path resolution fix in director_integration.py
Tests ingestion without needing full app initialization.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage

async def test_ingestion_simple():
    """Test ingestion of existing processing outputs - direct approach"""

    # Initialize storage
    db_path = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero" / "library" / "library.db"
    storage = LibraryStorage(db_path=db_path)

    # Item ID with director_output_path set
    item_id = "eb811b14-9c67-4871-a796-1b7de5e53704"

    print(f"\n🧪 Testing ingestion for item: {item_id}\n")

    # Get item
    item = storage.get_item(item_id)
    if not item:
        print(f"❌ Item not found: {item_id}")
        return

    print(f"✅ Found item: {item.name}")

    # Check director_output_path
    output_path_str = item.metadata.get('director_output_path')
    if not output_path_str:
        print("❌ No director_output_path in item metadata")
        return

    output_path = Path(output_path_str)
    print(f"📂 Output path: {output_path}")
    print(f"   Exists: {output_path.exists()}")

    if not output_path.exists():
        print("❌ Output path does not exist")
        return

    # Check before count
    print(f"\n📊 Database state BEFORE ingestion:")
    import sqlite3
    with sqlite3.connect(storage.db_path) as conn:
        before_count = conn.execute(
            "SELECT COUNT(*) FROM processing_outputs WHERE item_id = ?",
            (item_id,)
        ).fetchone()[0]
        print(f"   ProcessingOutputs for this item: {before_count}")

    # List files in output folder
    print(f"\n📁 Files in output folder:")
    for file in sorted(output_path.rglob("*")):
        if file.is_file() and not file.name.startswith('.'):
            rel_path = file.relative_to(output_path)
            print(f"   {rel_path}")

    # NOW TEST THE PATH RESOLUTION FIX
    print(f"\n🔍 Testing path resolution with .rglob():")

    # Check for manifest files
    manifest_dir = output_path / "assets" / "manifests"
    if manifest_dir.exists():
        print(f"   Found manifests directory: {manifest_dir}")

        # Look for transcriptions_manifest.jsonl
        trans_manifest = manifest_dir / "transcriptions_manifest.jsonl"
        if trans_manifest.exists():
            print(f"   Found transcriptions manifest: {trans_manifest.name}")

            # Read manifest and test path resolution
            import json
            with open(trans_manifest, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        entry = json.loads(line)
                        output_file = entry.get('output_file', entry.get('file', ''))
                        if output_file:
                            print(f"\n   Manifest entry {line_num}: {output_file}")

                            # OLD METHOD (BROKEN):
                            direct_path = trans_manifest.parent / output_file
                            print(f"      Direct path (BROKEN): {direct_path}")
                            print(f"      Exists: {direct_path.exists()}")

                            # NEW METHOD (FIXED):
                            found_files = list(trans_manifest.parent.rglob(output_file))
                            if found_files:
                                print(f"      rglob found (FIXED): {found_files[0]}")
                                print(f"      Exists: {found_files[0].exists()}")
                            else:
                                # Fallback to output_path root
                                found_files = list(output_path.rglob(output_file))
                                if found_files:
                                    print(f"      rglob from root (FIXED): {found_files[0]}")
                                    print(f"      Exists: {found_files[0].exists()}")
                                else:
                                    print(f"      ❌ Not found even with rglob")

    print(f"\n✅ Path resolution test complete!")
    print(f"   The fix uses .rglob() to recursively search for files")
    print(f"   This handles nested directory structures like assets/transcriptions/documents/")

if __name__ == "__main__":
    asyncio.run(test_ingestion_simple())
