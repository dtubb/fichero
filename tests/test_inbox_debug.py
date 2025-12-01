"""Debug script to test inbox creation"""

import asyncio
import tempfile
import shutil
from pathlib import Path

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage


async def test_inbox():
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp())
    print(f"Temp directory: {temp_dir}")

    try:
        # Create fresh database
        db_path = temp_dir / "test_inbox.db"
        print(f"Database path: {db_path}")
        print(f"Database exists before: {db_path.exists()}")

        # Create manager
        storage = LibraryStorage(str(db_path))
        manager = LibraryManager(storage)

        print(f"Database exists after init: {db_path.exists()}")

        # Check inboxes before creation
        collections_before = storage.get_all_collections()
        inboxes_before = [c for c in collections_before if c.metadata.get('is_inbox')]
        print(f"Inboxes before get_or_create: {len(inboxes_before)}")

        # Create inbox
        inbox_id = await manager.get_or_create_inbox()
        print(f"Created inbox ID: {inbox_id}")

        # Check inboxes after creation
        collections_after = storage.get_all_collections()
        inboxes_after = [c for c in collections_after if c.metadata.get('is_inbox')]
        print(f"Inboxes after get_or_create: {len(inboxes_after)}")

        for i, inbox in enumerate(inboxes_after):
            print(f"  Inbox {i+1}: {inbox.id} - {inbox.name} (created: {inbox.created_at})")

        # Try again
        inbox_id2 = await manager.get_or_create_inbox()
        print(f"Second call returned: {inbox_id2}")

        collections_final = storage.get_all_collections()
        inboxes_final = [c for c in collections_final if c.metadata.get('is_inbox')]
        print(f"Inboxes after second call: {len(inboxes_final)}")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(test_inbox())
