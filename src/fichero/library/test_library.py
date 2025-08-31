#!/usr/bin/env python3
"""
Test script for Fichero Library System

Run this to verify the library system is working correctly.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_library_system():
    """Test the library system functionality"""
    try:
        logger.info("Starting library system test")
        
        # Create a mock app object for testing
        class MockApp:
            class paths:
                data = Path(tempfile.mkdtemp())
        
        app = MockApp()
        
        # Import library components
        from fichero.library.library_manager import LibraryManager
        from fichero.library.ui_integration import LibraryUIIntegration
        
        logger.info("Testing library manager initialization")
        
        # Initialize library manager
        library_manager = LibraryManager(app)
        logger.info("✓ Library manager initialized")
        
        # Test collection creation
        logger.info("Testing collection creation")
        
        # Add external collection
        collection_id = await library_manager.add_collection(
            name="Test External Collection",
            collection_type="external",
            source_path="/tmp/test_external",
            description="Test collection for external path"
        )
        
        if collection_id:
            logger.info(f"✓ External collection created: {collection_id}")
        else:
            logger.error("✗ Failed to create external collection")
            return False
        
        # Add URL collection
        url_collection_id = await library_manager.get_collection_by_name("Test URL Collection")
        if not url_collection_id:
            url_collection_id = await library_manager.add_collection(
                name="Test URL Collection",
                collection_type="url",
                source_path="https://example.com/test",
                description="Test collection for URL resources"
            )
        
        if url_collection_id:
            logger.info(f"✓ URL collection created: {url_collection_id}")
        else:
            logger.error("✗ Failed to create URL collection")
            return False
        
        # Test getting collections
        logger.info("Testing collection retrieval")
        
        collections = await library_manager.get_all_collections()
        logger.info(f"✓ Retrieved {len(collections)} collections")
        
        # Test collection by name
        collection = await library_manager.get_collection_by_name("Test External Collection")
        if collection:
            logger.info(f"✓ Found collection by name: {collection.name}")
        else:
            logger.error("✗ Failed to find collection by name")
            return False
        
        # Test adding items
        logger.info("Testing item addition")
        
        # Create a test file
        test_file = Path(app.paths.data) / "test_file.txt"
        test_file.write_text("Test content")
        
        item_id = await library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="file",
            source=str(test_file),
            name="test_file.txt",
            operation="copy"
        )
        
        if item_id:
            logger.info(f"✓ Item added to collection: {item_id}")
        else:
            logger.error("✗ Failed to add item to collection")
            return False
        
        # Test getting collection items
        items = await library_manager.get_collection_items(collection_id)
        logger.info(f"✓ Retrieved {len(items)} items from collection")
        
        # Test processing result
        logger.info("Testing processing result addition")
        
        result_id = await library_manager.add_processing_result(
            item_id=item_id,
            workflow="test_workflow",
            status="success",
            output_paths=["/tmp/test_output.docx"],
            logs_path="/tmp/test_logs",
            metadata={"test": True}
        )
        
        if result_id:
            logger.info(f"✓ Processing result added: {result_id}")
        else:
            logger.error("✗ Failed to add processing result")
            return False
        
        # Test getting processing history
        history = await library_manager.get_processing_history(item_id)
        logger.info(f"✓ Retrieved {len(history)} processing results")
        
        # Test library stats
        logger.info("Testing library statistics")
        
        stats = await library_manager.get_library_stats()
        logger.info(f"✓ Library stats: {stats}")
        
        # Test UI integration
        logger.info("Testing UI integration")
        
        ui_integration = LibraryUIIntegration(library_manager)
        logger.info("✓ UI integration initialized")
        
        # Test getting collections for UI
        ui_collections = await ui_integration.get_collections_for_ui()
        logger.info(f"✓ UI collections: {len(ui_collections)}")
        
        # Test external collection scanning
        logger.info("Testing external collection scanning")
        
        external_status = await library_manager.scan_external_collections()
        logger.info(f"✓ External collection status: {external_status}")
        
        logger.info("✓ All library system tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Library system test failed: {e}")
        return False


async def test_import_export():
    """Test import/export functionality"""
    try:
        logger.info("Starting import/export test")
        
        # Create a mock app object for testing
        class MockApp:
            class paths:
                data = Path(tempfile.mkdtemp())
        
        app = MockApp()
        
        # Import library components
        from fichero.library.library_manager import LibraryManager
        from fichero.library.import_export import CollectionExporter, CollectionImporter
        
        # Initialize library manager
        library_manager = LibraryManager(app)
        
        # Create a test collection
        collection_id = await library_manager.add_collection(
            name="Test Export Collection",
            collection_type="external",
            source_path="/tmp/test_export",
            description="Test collection for export/import"
        )
        
        if not collection_id:
            logger.error("✗ Failed to create test collection for export")
            return False
        
        # Add a test item
        item_id = await library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="file",
            source="/tmp/test_file.txt",
            name="test_file.txt",
            operation="link"
        )
        
        if not item_id:
            logger.error("✗ Failed to add test item for export")
            return False
        
        # Test export
        logger.info("Testing collection export")
        
        export_path = Path(app.paths.data) / "test_export.zip"
        exporter = CollectionExporter(library_manager.storage)
        
        success = exporter.export_collection(collection_id, export_path, include_files=False)
        if success:
            logger.info(f"✓ Collection exported to: {export_path}")
        else:
            logger.error("✗ Failed to export collection")
            return False
        
        # Test import
        logger.info("Testing collection import")
        
        importer = CollectionImporter(library_manager.storage)
        
        # Import with new name
        imported_id = await importer.import_collection(export_path, "Imported Test Collection")
        if imported_id:
            logger.info(f"✓ Collection imported with ID: {imported_id}")
        else:
            logger.error("✗ Failed to import collection")
            return False
        
        # Verify imported collection
        imported_collection = await library_manager.get_collection(imported_id)
        if imported_collection:
            logger.info(f"✓ Imported collection verified: {imported_collection.name}")
        else:
            logger.error("✗ Failed to verify imported collection")
            return False
        
        logger.info("✓ All import/export tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Import/export test failed: {e}")
        return False


async def main():
    """Run all tests"""
    logger.info("=" * 50)
    logger.info("FICHERO LIBRARY SYSTEM TEST SUITE")
    logger.info("=" * 50)
    
    # Test library system
    library_test_passed = await test_library_system()
    
    # Test import/export
    import_export_test_passed = await test_import_export()
    
    # Summary
    logger.info("=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)
    
    if library_test_passed:
        logger.info("✓ Library System: PASSED")
    else:
        logger.error("✗ Library System: FAILED")
    
    if import_export_test_passed:
        logger.info("✓ Import/Export: PASSED")
    else:
        logger.error("✗ Import/Export: FAILED")
    
    if library_test_passed and import_export_test_passed:
        logger.info("🎉 ALL TESTS PASSED! Library system is working correctly.")
        return True
    else:
        logger.error("💥 SOME TESTS FAILED! Please check the errors above.")
        return False


if __name__ == "__main__":
    # Run tests
    success = asyncio.run(main())
    
    # Exit with appropriate code
    exit(0 if success else 1) 