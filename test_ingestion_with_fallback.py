#!/usr/bin/env python3
"""
Test script to verify ingestion with subdirectory fallback works
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager
from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.storage import LibraryStorage

# Initialize storage with default DB path
db_path = Path.home() / "Library/Application Support/ca.tubb.fichero/library/library.db"
storage = LibraryStorage(db_path)

# Create a minimal library manager mock
class MockApp:
    pass

library_manager = LibraryManager(MockApp())
library_manager.storage = storage
director_integration = DirectorIntegrationService(library_manager)

# Test with the existing workflow output
output_path = Path("/Users/dtubb/Library/Application Support/ca.tubb.fichero/library/collections/866686c9-0569-4e51-aebb-cb0efe904f76/outputs/2025-11-23_08-23-01/TranscribeTest/1931_Antonio_Asprilla_pide_que_se_haga_efectiva_una_multa_a_M.C._Marshall_y_Manuel_A._Pen_a__Istmina")

# Check if path exists
if not output_path.exists():
    print(f"❌ Output path doesn't exist: {output_path}")
    sys.exit(1)

print(f"✅ Output path exists: {output_path}")
print()

# Check for workflow manifest
manifest_file = output_path / "workflow_manifest.json"
if not manifest_file.exists():
    print(f"❌ No workflow_manifest.json found")
    sys.exit(1)

print(f"✅ Found workflow_manifest.json")
print()

# Check for transcription manifest
trans_manifest = output_path / "assets" / "transcriptions" / "transcriptions_manifest.jsonl"
if not trans_manifest.exists():
    print(f"❌ No transcriptions_manifest.jsonl found")
    sys.exit(1)

print(f"✅ Found transcriptions_manifest.jsonl")
print()

# Read manifest content
import json
print("📄 Manifest content:")
with open(trans_manifest) as f:
    for i, line in enumerate(f, 1):
        record = json.loads(line)
        print(f"  Record {i}:")
        print(f"    outputs: {record.get('outputs', [])}")
        print(f"    source: {record.get('source')}")
        print()

# Check for actual transcription files
trans_dir = output_path / "assets" / "transcriptions" / "documents"
if trans_dir.exists():
    trans_files = list(trans_dir.glob("*.txt"))
    print(f"✅ Found {len(trans_files)} transcription files in documents/:")
    for f in trans_files:
        print(f"    {f.name} ({f.stat().st_size} bytes)")
    print()
else:
    print(f"❌ No documents/ subdirectory found")
    sys.exit(1)

# Now test if ingestion can find these files despite wrong paths in manifest
print("🔍 Testing ingestion with subdirectory fallback...")
print()

# Get collection and item IDs
collection_id = "866686c9-0569-4e51-aebb-cb0efe904f76"
item_id = "838ecabb-03b7-4f70-8982-f72300723036"

# Check if there's a processing_history record for this workflow
import sqlite3
db_path = Path.home() / "Library/Application Support/ca.tubb.fichero/library/library.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT id, workflow_name, plan_name, status
    FROM processing_history
    WHERE output_path LIKE '%2025-11-23_08-23-01%'
""")
history = cursor.fetchall()

if history:
    print(f"✅ Found processing_history record:")
    for h in history:
        print(f"    ID: {h[0]}")
        print(f"    Workflow: {h[1]}")
        print(f"    Plan: {h[2]}")
        print(f"    Status: {h[3]}")
    print()

    processing_result_id = history[0][0]
else:
    print("⚠️  No processing_history record found - creating fake one for test")
    import uuid
    processing_result_id = str(uuid.uuid4())
    print()

# Check current processing_outputs count
cursor.execute("SELECT COUNT(*) FROM processing_outputs")
before_count = cursor.fetchone()[0]
print(f"📊 Processing outputs before ingestion: {before_count}")
print()

# Try to ingest
print("🚀 Running ingestion...")
try:
    director_integration._ingest_processing_outputs(
        output_path,
        processing_result_id,
        collection_id,
        item_id
    )
    print("✅ Ingestion completed successfully!")
except Exception as e:
    print(f"❌ Ingestion failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Check after count
cursor.execute("SELECT COUNT(*) FROM processing_outputs")
after_count = cursor.fetchone()[0]
print(f"📊 Processing outputs after ingestion: {after_count}")
print(f"   New records created: {after_count - before_count}")
print()

# Show the records
if after_count > before_count:
    cursor.execute("""
        SELECT id, step_name, output_type, output_path, file_size
        FROM processing_outputs
        WHERE processing_result_id = ?
    """, (processing_result_id,))

    print("📋 New processing_output records:")
    for record in cursor.fetchall():
        print(f"    ID: {record[0]}")
        print(f"    Step: {record[1]}")
        print(f"    Type: {record[2]}")
        print(f"    Path: {record[3]}")
        print(f"    Size: {record[4]} bytes")
        print()

conn.close()

print("✅ TEST COMPLETE!")
