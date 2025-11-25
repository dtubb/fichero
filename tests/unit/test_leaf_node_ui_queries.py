"""
Test leaf vs node metadata queries for UI contexts

Validates that the UI can properly distinguish between:
- Leaf-level metadata: Individual file outputs (enhanced images, transcriptions)
- Node-level metadata: Collection outputs (catalogues, summaries, analyses)
"""

import tempfile
import unittest
from pathlib import Path

from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem, ExtractedMetadata
from fichero.library.storage import LibraryStorage


class TestLeafNodeUIQueries(unittest.TestCase):
    """Test UI queries for leaf vs node metadata"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "test_ui_library.db"
        self.storage = LibraryStorage(str(self.storage_path))
        self.library_manager = LibraryManager(self.storage)

        # Create test collection
        self.collection = Collection(
            id="ui-test-collection",
            name="UI Test Collection",
            metadata={"description": "Collection for testing UI metadata queries"}
        )
        self.storage.add_collection(self.collection)

        # Create test items (documents)
        self.item1 = CollectionItem(
            id="doc-001",
            collection_id=self.collection.id,
            name="1931_document_01.jpg",
            type="file"
        )
        self.item2 = CollectionItem(
            id="doc-002",
            collection_id=self.collection.id,
            name="1931_document_02.jpg",
            type="file"
        )
        self.storage.add_collection_item(self.item1)
        self.storage.add_collection_item(self.item2)

        # Create sample metadata reflecting real workflow outputs
        self._create_sample_metadata()

    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def _create_sample_metadata(self):
        """Create sample metadata reflecting real workflow structure"""

        # LEAF-LEVEL METADATA (file-specific outputs)

        # Enhanced images (per document)
        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="enhance-001",
            collection_id=self.collection.id,
            item_id=self.item1.id,
            collection_level=False,
            schema_type="prepared_image",
            source_label="enhance",
            version=1,
            schema_version="1.0",
            key="file_path",
            value="assets/enhanced/1931_document_01.jpg",
            confidence=1.0
        ))

        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="enhance-002",
            collection_id=self.collection.id,
            item_id=self.item2.id,
            collection_level=False,
            schema_type="prepared_image",
            source_label="enhance",
            version=1,
            schema_version="1.0",
            key="file_path",
            value="assets/enhanced/1931_document_02.jpg",
            confidence=1.0
        ))

        # Transcriptions (per document)
        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="transcribe-001",
            collection_id=self.collection.id,
            item_id=self.item1.id,
            collection_level=False,
            schema_type="transcription",
            source_label="ai_qwen",
            version=1,
            schema_version="1.0",
            key="text",
            value="Registro Civil de Istmina. Defunción de Antonio Asprilla, edad 45 años...",
            confidence=0.92
        ))

        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="transcribe-002",
            collection_id=self.collection.id,
            item_id=self.item2.id,
            collection_level=False,
            schema_type="transcription",
            source_label="ai_qwen",
            version=1,
            schema_version="1.0",
            key="text",
            value="Municipio de Istmina. Solicitud de multa contra M.C. Marshall...",
            confidence=0.88
        ))

        # NODE-LEVEL METADATA (collection-wide outputs)

        # Collection catalogue
        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="catalogue-001",
            collection_id=self.collection.id,
            item_id=None,  # Collection-level
            collection_level=True,
            schema_type="catalogue",
            source_label="ai_catalogue",
            version=1,
            schema_version="1.0",
            key="description",
            value="Historical documents from Istmina civil registry, 1931 period",
            confidence=0.90
        ))

        # Timeline analysis
        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="catalogue-002",
            collection_id=self.collection.id,
            item_id=None,
            collection_level=True,
            schema_type="catalogue",
            source_label="ai_catalogue",
            version=1,
            schema_version="1.0",
            key="timeline",
            value="1931: Period of civil registry documentation and municipal administration",
            confidence=0.85
        ))

        # People mentioned
        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="catalogue-003",
            collection_id=self.collection.id,
            item_id=None,
            collection_level=True,
            schema_type="catalogue",
            source_label="ai_catalogue",
            version=1,
            schema_version="1.0",
            key="people",
            value="Antonio Asprilla, M.C. Marshall, Manuel A. Peña",
            confidence=0.93
        ))

        # Places mentioned
        self.storage.add_extracted_metadata(ExtractedMetadata(
            processing_output_id="catalogue-004",
            collection_id=self.collection.id,
            item_id=None,
            collection_level=True,
            schema_type="catalogue",
            source_label="ai_catalogue",
            version=1,
            schema_version="1.0",
            key="places",
            value="Istmina, Registro Civil, Municipio",
            confidence=0.91
        ))

    def test_preview_view_queries(self):
        """Test queries needed for preview view (should load leaf-level data)"""

        # Preview view needs enhanced images for specific documents
        enhanced_images = self.storage.get_leaf_level_metadata(
            collection_id=self.collection.id,
            schema_type="prepared_image"
        )

        self.assertEqual(len(enhanced_images), 2)
        # Should have one for each document
        item_ids = {meta.item_id for meta in enhanced_images}
        self.assertEqual(item_ids, {self.item1.id, self.item2.id})

        # Preview view needs transcriptions for specific documents
        transcriptions = self.storage.get_leaf_level_metadata(
            collection_id=self.collection.id,
            schema_type="transcription"
        )

        self.assertEqual(len(transcriptions), 2)
        # Check specific transcription content
        doc1_transcription = [t for t in transcriptions if t.item_id == self.item1.id][0]
        self.assertIn("Antonio Asprilla", doc1_transcription.value)

    def test_collection_view_queries(self):
        """Test queries needed for collection view (should load node-level data)"""

        # Collection view needs collection-wide catalogues
        catalogues = self.storage.get_collection_level_metadata(
            collection_id=self.collection.id,
            schema_type="catalogue"
        )

        self.assertEqual(len(catalogues), 4)  # description, timeline, people, places
        # All should be collection-level (no item_id)
        for catalogue in catalogues:
            self.assertIsNone(catalogue.item_id)
            self.assertTrue(catalogue.collection_level)

        # Get specific catalogue components
        description = [c for c in catalogues if c.key == "description"][0]
        self.assertIn("Historical documents from Istmina", description.value)

        timeline = [c for c in catalogues if c.key == "timeline"][0]
        self.assertIn("1931", timeline.value)

        people = [c for c in catalogues if c.key == "people"][0]
        self.assertIn("Antonio Asprilla", people.value)

        places = [c for c in catalogues if c.key == "places"][0]
        self.assertIn("Istmina", places.value)

    def test_specific_document_queries(self):
        """Test queries for specific document in preview (should only load its leaf data)"""

        # When viewing a specific document, load only its metadata
        doc1_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.item1.id,
            collection_level=False  # Only file-level data
        )

        # Should have enhanced image and transcription
        self.assertEqual(len(doc1_metadata), 2)

        schemas = {meta.schema_type for meta in doc1_metadata}
        self.assertEqual(schemas, {"prepared_image", "transcription"})

        # All should be for this specific item
        for meta in doc1_metadata:
            self.assertEqual(meta.item_id, self.item1.id)
            self.assertFalse(meta.collection_level)

    def test_mixed_queries_separation(self):
        """Test that leaf and node queries don't interfere with each other"""

        # Query all metadata for collection
        all_metadata = self.storage.get_extracted_metadata_by_collection(self.collection.id)
        self.assertEqual(len(all_metadata), 8)  # 4 leaf + 4 node

        # Separate by level
        leaf_only = [m for m in all_metadata if not m.collection_level]
        node_only = [m for m in all_metadata if m.collection_level]

        self.assertEqual(len(leaf_only), 4)  # 2 enhanced images + 2 transcriptions
        self.assertEqual(len(node_only), 4)  # description + timeline + people + places

        # Verify leaf metadata has item_ids
        for meta in leaf_only:
            self.assertIsNotNone(meta.item_id)
            self.assertIn(meta.item_id, [self.item1.id, self.item2.id])

        # Verify node metadata has no item_ids
        for meta in node_only:
            self.assertIsNone(meta.item_id)

    def test_schema_type_filtering(self):
        """Test filtering by schema type across leaf/node levels"""

        # Get all transcriptions (should be leaf-level only)
        transcriptions = self.storage.get_extracted_metadata_by_collection(
            self.collection.id,
            schema_type="transcription"
        )
        self.assertEqual(len(transcriptions), 2)
        for trans in transcriptions:
            self.assertFalse(trans.collection_level)
            self.assertIsNotNone(trans.item_id)

        # Get all catalogues (should be node-level only)
        catalogues = self.storage.get_extracted_metadata_by_collection(
            self.collection.id,
            schema_type="catalogue"
        )
        self.assertEqual(len(catalogues), 4)
        for cat in catalogues:
            self.assertTrue(cat.collection_level)
            self.assertIsNone(cat.item_id)

    def test_confidence_ordering(self):
        """Test that metadata is properly ordered by confidence/version"""

        # Get people metadata (should be highest confidence node-level)
        people_metadata = self.storage.get_collection_level_metadata(
            collection_id=self.collection.id,
            key="people"
        )

        self.assertEqual(len(people_metadata), 1)
        self.assertEqual(people_metadata[0].confidence, 0.93)  # Highest among catalogue data
        self.assertIn("Antonio Asprilla", people_metadata[0].value)


if __name__ == "__main__":
    unittest.main()