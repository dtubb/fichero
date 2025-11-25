#!/usr/bin/env python3
"""
Investigation script to understand the exact data flow issues
"""

import sys
import logging
import asyncio
import sqlite3
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from fichero.library.library_manager import LibraryManager

async def investigate_data_flow():
    """Investigate the exact data flow issues"""

    print("=" * 70)
    print("FICHERO DATA FLOW INVESTIGATION")
    print("=" * 70)

    # Initialize library manager
    print("\n1. Initializing LibraryManager...")
    library_manager = LibraryManager(app=None)

    # Get database path for direct queries
    db_path = library_manager.storage.db_path
    print(f"Database path: {db_path}")

    # Check collections
    print("\n2. Checking collections...")
    collections = await library_manager.get_all_collections()
    print(f"Total collections: {len(collections)}")

    # Find collections with processing results
    print("\n3. Finding collections with processing results...")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get all processing results
        cursor.execute("""
            SELECT pr.id, pr.item_id, pr.workflow, pr.status,
                   pr.output_paths, pr.completed_at,
                   i.name as item_name, c.name as collection_name
            FROM processing_results pr
            LEFT JOIN items i ON pr.item_id = i.id
            LEFT JOIN collections c ON i.collection_id = c.id
            ORDER BY pr.completed_at DESC
        """)

        processing_results = cursor.fetchall()
        print(f"Total processing results: {len(processing_results)}")

        for i, result in enumerate(processing_results[:5]):  # Show first 5
            pr_id, item_id, workflow, status, output_paths, completed_at, item_name, collection_name = result
            print(f"\n  {i+1}. Processing Result ID: {pr_id}")
            print(f"     Item: {item_name} (id: {item_id})")
            print(f"     Collection: {collection_name}")
            print(f"     Workflow: {workflow}")
            print(f"     Status: {status}")
            print(f"     Output paths: {output_paths}")
            print(f"     Completed: {completed_at}")

            # Check for ProcessingOutputs
            cursor.execute("""
                SELECT COUNT(*) FROM processing_outputs
                WHERE processing_result_id = ?
            """, (pr_id,))
            output_count = cursor.fetchone()[0]
            print(f"     ProcessingOutputs in DB: {output_count}")

            if output_count == 0:
                print(f"     ❌ NO ProcessingOutputs found for this result!")

                # Check if output paths exist
                if output_paths:
                    import json
                    try:
                        paths = json.loads(output_paths) if isinstance(output_paths, str) else output_paths
                        for path_str in paths:
                            output_path = Path(path_str)
                            print(f"     Checking path: {output_path}")
                            print(f"     Exists: {output_path.exists()}")

                            if output_path.exists():
                                # Check for workflow manifest
                                manifest_path = output_path / "workflow_manifest.json"
                                print(f"     workflow_manifest.json exists: {manifest_path.exists()}")

                                if manifest_path.exists():
                                    print(f"     ✅ Manifest file found - output ingestion should work!")

                                    # Find tool manifests
                                    tool_manifests = list(output_path.rglob("*_manifest.jsonl"))
                                    print(f"     Tool manifests found: {len(tool_manifests)}")
                                    for tm in tool_manifests:
                                        rel_path = tm.relative_to(output_path)
                                        size = tm.stat().st_size
                                        print(f"       - {rel_path} ({size} bytes)")

                    except Exception as e:
                        print(f"     Error checking paths: {e}")
            else:
                print(f"     ✅ Has ProcessingOutputs in database")

                # Show some ProcessingOutputs
                cursor.execute("""
                    SELECT output_type, output_path, file_format
                    FROM processing_outputs
                    WHERE processing_result_id = ?
                    LIMIT 3
                """, (pr_id,))
                outputs = cursor.fetchall()
                for output in outputs:
                    output_type, output_path, file_format = output
                    print(f"       - {output_type}: {output_path} ({file_format})")

            # Check for ExtractedMetadata
            cursor.execute("""
                SELECT COUNT(*) FROM extracted_metadata
                WHERE item_id = ? OR processing_output_id IN (
                    SELECT id FROM processing_outputs WHERE processing_result_id = ?
                )
            """, (item_id, pr_id))
            metadata_count = cursor.fetchone()[0]
            print(f"     ExtractedMetadata records: {metadata_count}")

            print("     " + "-" * 50)

    print("\n4. Summary of findings:")
    print("   - Processing results exist in database")
    print("   - Some have ProcessingOutputs, some don't")
    print("   - Need to check ingestion flow for missing outputs")

if __name__ == "__main__":
    asyncio.run(investigate_data_flow())