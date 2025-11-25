#!/usr/bin/env python3
"""
Investigation script to understand the exact data flow issues - FIXED SCHEMA
"""

import sys
import logging
import asyncio
import sqlite3
import json
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
    """Investigate the exact data flow issues with correct schema"""

    print("=" * 70)
    print("FICHERO DATA FLOW INVESTIGATION (FIXED SCHEMA)")
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

    # Find collections with processing history
    print("\n3. Finding collections with processing history...")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get all processing history
        cursor.execute("""
            SELECT ph.id, ph.item_id, ph.workflow, ph.status,
                   ph.output_paths, ph.completed_at,
                   ci.name as item_name, c.name as collection_name, ci.collection_id
            FROM processing_history ph
            LEFT JOIN collection_items ci ON ph.item_id = ci.id
            LEFT JOIN collections c ON ci.collection_id = c.id
            ORDER BY ph.completed_at DESC
        """)

        processing_results = cursor.fetchall()
        print(f"Total processing history records: {len(processing_results)}")

        for i, result in enumerate(processing_results):
            ph_id, item_id, workflow, status, output_paths, completed_at, item_name, collection_name, collection_id = result
            print(f"\n  {i+1}. Processing History ID: {ph_id}")
            print(f"     Item: {item_name} (id: {item_id})")
            print(f"     Collection: {collection_name} (id: {collection_id})")
            print(f"     Workflow: {workflow}")
            print(f"     Status: {status}")
            print(f"     Output paths: {output_paths}")
            print(f"     Completed: {completed_at}")

            # Check for ProcessingOutputs (using processing_history.id as processing_result_id)
            cursor.execute("""
                SELECT COUNT(*) FROM processing_outputs
                WHERE processing_result_id = ?
            """, (ph_id,))
            output_count = cursor.fetchone()[0]
            print(f"     ProcessingOutputs in DB: {output_count}")

            if output_count == 0:
                print(f"     ❌ NO ProcessingOutputs found for this history record!")

                # Check if output paths exist
                if output_paths:
                    try:
                        paths = json.loads(output_paths) if isinstance(output_paths, str) else [output_paths]
                        for path_str in paths:
                            output_path = Path(path_str)
                            print(f"     Checking path: {output_path}")
                            print(f"     Exists: {output_path.exists()}")

                            if output_path.exists():
                                # Check for workflow manifest
                                manifest_path = output_path / "workflow_manifest.json"
                                print(f"     workflow_manifest.json exists: {manifest_path.exists()}")

                                if manifest_path.exists():
                                    print(f"     ✅ Manifest file found - INGESTION SHOULD WORK!")

                                    # Read the workflow manifest
                                    with open(manifest_path, 'r') as f:
                                        manifest_data = json.load(f)

                                    print(f"     Workflow: {manifest_data.get('workflow', {}).get('workflow_name', 'Unknown')}")
                                    print(f"     Plan: {manifest_data.get('workflow', {}).get('plan_name', 'Unknown')}")
                                    print(f"     Steps: {len(manifest_data.get('steps', []))}")

                                    # Find tool manifests
                                    tool_manifests = list(output_path.rglob("*_manifest.jsonl"))
                                    print(f"     Tool manifests found: {len(tool_manifests)}")
                                    for tm in tool_manifests:
                                        rel_path = tm.relative_to(output_path)
                                        size = tm.stat().st_size
                                        print(f"       - {rel_path} ({size} bytes)")

                                        # Read first few lines to check content
                                        if size > 0:
                                            with open(tm, 'r') as f:
                                                lines = 0
                                                for line in f:
                                                    if lines >= 2:
                                                        break
                                                    if line.strip():
                                                        try:
                                                            entry = json.loads(line)
                                                            outputs = entry.get('outputs', entry.get('output_file', []))
                                                            if outputs:
                                                                print(f"         Sample output: {outputs[0] if isinstance(outputs, list) else outputs}")
                                                        except:
                                                            print(f"         Raw line: {line.strip()[:50]}...")
                                                        lines += 1

                                    # CHECK THE KEY ISSUE: Can DirectorIntegrationService find this data?
                                    print(f"     🧪 TESTING INGESTION SIMULATION...")

                                    # Simulate the ingestion call
                                    from fichero.director.workflow_manifest import WorkflowManifest

                                    # Try to read manifest (this is what ingestion does)
                                    workflow_manifest = WorkflowManifest.read_manifest(output_path)
                                    if workflow_manifest:
                                        print(f"     ✅ WorkflowManifest.read_manifest() SUCCESS")
                                        steps = workflow_manifest.get('steps', [])
                                        print(f"     Steps found in manifest: {len(steps)}")
                                        for step in steps:
                                            step_name = step.get('name', 'Unknown')
                                            step_status = step.get('status', 'Unknown')
                                            manifest_file = step.get('manifest_file', 'None')
                                            print(f"       - {step_name} ({step_status}): {manifest_file}")
                                    else:
                                        print(f"     ❌ WorkflowManifest.read_manifest() FAILED")

                                else:
                                    print(f"     ❌ workflow_manifest.json NOT FOUND - ingestion will fail")
                            else:
                                print(f"     ❌ Output path DOES NOT EXIST - processing may have failed")

                    except Exception as e:
                        print(f"     Error checking paths: {e}")
            else:
                print(f"     ✅ Has ProcessingOutputs in database")

                # Show some ProcessingOutputs
                cursor.execute("""
                    SELECT output_type, output_path, file_format, step_name
                    FROM processing_outputs
                    WHERE processing_result_id = ?
                    LIMIT 3
                """, (ph_id,))
                outputs = cursor.fetchall()
                for output in outputs:
                    output_type, output_path, file_format, step_name = output
                    print(f"       - {step_name}: {output_type} -> {output_path} ({file_format})")

            # Check for ExtractedMetadata
            cursor.execute("""
                SELECT COUNT(*) FROM extracted_metadata
                WHERE item_id = ? OR processing_output_id IN (
                    SELECT id FROM processing_outputs WHERE processing_result_id = ?
                )
            """, (item_id, ph_id))
            metadata_count = cursor.fetchone()[0]
            print(f"     ExtractedMetadata records: {metadata_count}")

            print("     " + "-" * 50)

    print("\n4. KEY FINDINGS:")
    print("   - Database uses 'processing_history' table, not 'processing_results'")
    print("   - Some history records have ProcessingOutputs, some don't")
    print("   - Need to identify why some ingestion calls fail")
    print("   - Check if collection_id validation is the issue")

if __name__ == "__main__":
    asyncio.run(investigate_data_flow())