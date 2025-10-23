#!/usr/bin/env python3
"""
Debug test: Library process command test with detailed logging
"""
import asyncio
import sys
import logging
from pathlib import Path

# Set up logging FIRST
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager
from fichero.director.director_service import FicheroDirector
from fichero.library.director_integration import DirectorIntegrationService

async def test_library_process():
    """Test library processing with debug output"""
    print("\n" + "="*60)
    print("LIBRARY PROCESS DEBUG TEST")
    print("="*60)

    try:
        # Initialize library with mock app
        logger.info("Step 1: Creating mock app...")
        class MockApp:
            pass

        mock_app = MockApp()
        logger.info("✅ Mock app created")

        # Initialize library manager
        logger.info("Step 2: Initializing library manager...")
        library_manager = LibraryManager(mock_app)
        logger.info(f"✅ Library manager initialized at: {library_manager.library_path}")

        # Initialize Director
        logger.info("Step 3: Initializing Director...")
        director = FicheroDirector()
        logger.info("✅ Director instance created")

        # Initialize backend
        logger.info("Step 4: Initializing Director backend...")
        if not director.initialize_backend():
            logger.error("❌ Failed to initialize Director backend")
            return
        logger.info("✅ Director backend initialized")

        # Initialize director integration
        logger.info("Step 5: Creating DirectorIntegrationService...")
        mock_app.director_integration = DirectorIntegrationService(
            app=mock_app,
            library_manager=library_manager,
            director=director
        )
        logger.info("✅ DirectorIntegrationService created")

        # Get collection
        collection_id = "861c3913-0002-437a-84b2-9f426f71b638"
        logger.info(f"Step 6: Loading collection {collection_id}...")
        collections = await library_manager.get_all_collections()
        logger.info(f"Found {len(collections)} total collections")

        collection = None
        for coll in collections:
            if coll.id == collection_id:
                collection = coll
                break

        if not collection:
            logger.error(f"❌ Collection {collection_id} not found")
            return
        logger.info(f"✅ Found collection: {collection.name}")

        # Get items
        logger.info("Step 7: Loading collection items...")
        items = await library_manager.get_collection_items(collection_id)
        logger.info(f"Found {len(items)} items in collection")

        if not items:
            logger.error("❌ No items in collection")
            return

        item_ids = [item.id for item in items]
        logger.info(f"Item IDs: {item_ids}")

        # Process items
        logger.info("Step 8: Calling process_items()...")
        logger.info("  This is where the hang might occur...")

        task_ids = await mock_app.director_integration.process_items(
            collection_id=collection_id,
            item_ids=item_ids,
            plan_name="Test Images Only",
            workflow_name="ImagePrep"
        )

        logger.info(f"✅ process_items() returned: {task_ids}")
        logger.info(f"Submitted {len(task_ids)} tasks")

        print("\n" + "="*60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*60)

    except Exception as e:
        logger.error(f"❌ Exception occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_library_process())
