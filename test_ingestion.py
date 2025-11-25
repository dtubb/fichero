"""
Test script to manually ingest existing processing outputs into the database.
This tests the path resolution fix in director_integration.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.director_integration import DirectorIntegrationService

async def test_ingestion():
    """Test ingestion of existing processing outputs"""
    # Initialize storage, library_manager, and director_integration
    from fichero.library.library_manager import LibraryManager
    from fichero.director.director_service import FicheroDirector

    db_path = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero" / "library" / "library.db"
    storage = LibraryStorage(db_path=db_path)

    # Create library_manager
    library_manager = LibraryManager(storage=storage)

    # Create director (minimal initialization for testing)
    director = FicheroDirector()

    # Create minimal mock app object
    class MockApp:
        def __init__(self):
            self.library_manager = library_manager
            self.director = director

    mock_app = MockApp()

    # Create director_integration service
    director_service = DirectorIntegrationService(mock_app, library_manager, director)

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
    before_count = storage.connection.execute(
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

    # Trigger ingestion via director_integration
    print(f"\n🔄 Triggering ingestion...")

    # Call _ingest_processing_outputs directly
    await director_service._ingest_processing_outputs(
        item_id=item_id,
        output_path=output_path
    )

    # Check after count
    print(f"\n📊 Database state AFTER ingestion:")
    after_count = storage.connection.execute(
        "SELECT COUNT(*) FROM processing_outputs WHERE item_id = ?",
        (item_id,)
    ).fetchone()[0]
    print(f"   ProcessingOutputs for this item: {after_count}")
    print(f"   Records created: {after_count - before_count}")

    if after_count > before_count:
        print("\n✅ SUCCESS: Ingestion created ProcessingOutput records!")

        # Show details
        outputs = storage.connection.execute(
            "SELECT tool_name, file_path, created_at FROM processing_outputs WHERE item_id = ? ORDER BY step_order",
            (item_id,)
        ).fetchall()

        print(f"\n📋 ProcessingOutput records:")
        for tool_name, file_path, created_at in outputs:
            print(f"   - {tool_name}: {Path(file_path).name}")
    else:
        print("\n❌ FAIL: No ProcessingOutput records were created")
        print("   This means the path resolution is still failing")

if __name__ == "__main__":
    asyncio.run(test_ingestion())
