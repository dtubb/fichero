"""
Unit tests for convert_to_word tool

Tests the Word document generation tool with focus on skip_processing mode.
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
import json
from datetime import datetime
from docx import Document

from fichero.tools.convert_to_word import convert_to_word_batch


class TestConvertToWord(unittest.TestCase):
    """Test convert_to_word functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temp directory structure
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir) / "test_workspace"
        self.test_dir.mkdir(parents=True)

        # Create test folders
        self.transcriptions_dir = self.test_dir / "transcriptions"
        self.images_dir = self.test_dir / "images"
        self.output_dir = self.test_dir / "output"

        self.transcriptions_dir.mkdir()
        self.images_dir.mkdir()
        self.output_dir.mkdir()

        # Create test transcription manifest with folder structure
        self.manifest_path = self.transcriptions_dir / "transcriptions_manifest.jsonl"
        self.test_entries = [
            {
                "source": "folder1/doc1_page1.txt",
                "outputs": ["folder1/doc1_page1.txt"],
                "success": True
            },
            {
                "source": "folder1/doc1_page2.txt",
                "outputs": ["folder1/doc1_page2.txt"],
                "success": True
            },
            {
                "source": "folder2/doc2_page1.txt",
                "outputs": ["folder2/doc2_page1.txt"],
                "success": True
            }
        ]

        with open(self.manifest_path, 'w') as f:
            for entry in self.test_entries:
                f.write(json.dumps(entry) + "\n")

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_skip_processing_creates_empty_files(self):
        """Test that skip_processing=True creates empty Word files"""
        # Run with skip_processing enabled
        stats = convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=self.manifest_path,
            output_folder=self.output_dir,
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify statistics
        self.assertEqual(stats['total'], 3, "Should process all 3 entries")
        self.assertEqual(stats['success'], 3, "All entries should succeed")
        self.assertEqual(stats['failed'], 0, "No entries should fail")

        # Verify output files were created
        folder1_doc = self.output_dir / "folder1" / "folder1.docx"
        folder2_doc = self.output_dir / "folder2" / "folder2.docx"

        self.assertTrue(folder1_doc.exists(), "folder1 Word doc should exist")
        self.assertTrue(folder2_doc.exists(), "folder2 Word doc should exist")

        # Verify files are valid (empty) Word documents
        doc1 = Document(str(folder1_doc))
        doc2 = Document(str(folder2_doc))

        self.assertIsNotNone(doc1, "folder1 doc should be valid Word document")
        self.assertIsNotNone(doc2, "folder2 doc should be valid Word document")

    def test_skip_processing_creates_manifest(self):
        """Test that skip_processing creates proper output manifest"""
        # Run with skip_processing enabled
        convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=self.manifest_path,
            output_folder=self.output_dir,
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify output manifest exists
        output_manifest = self.output_dir / "convert_to_word_manifest.jsonl"
        self.assertTrue(output_manifest.exists(), "Output manifest should exist")

        # Read and verify manifest entries
        entries = []
        with open(output_manifest, 'r') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        self.assertEqual(len(entries), 3, "Manifest should have 3 entries")

        # Check each entry has required fields
        for entry in entries:
            self.assertIn('source', entry, "Entry should have source field")
            self.assertIn('outputs', entry, "Entry should have outputs field")
            self.assertIn('processed_at', entry, "Entry should have processed_at field")
            self.assertIn('success', entry, "Entry should have success field")
            self.assertTrue(entry['success'], "Entry should be successful")
            self.assertIn('details', entry, "Entry should have details field")
            self.assertTrue(entry['details'].get('skip_processing'), "Should indicate skip_processing")

    def test_skip_processing_groups_by_folder(self):
        """Test that skip_processing correctly groups items by parent folder"""
        # Run with skip_processing enabled
        convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=self.manifest_path,
            output_folder=self.output_dir,
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify only 2 Word files created (one per folder, not one per entry)
        output_files = list(self.output_dir.rglob("*.docx"))
        self.assertEqual(len(output_files), 2, "Should create 2 Word docs (one per folder)")

        # Verify file paths
        file_names = {f.parent.name for f in output_files}
        self.assertEqual(file_names, {"folder1", "folder2"}, "Should create docs for both folders")

    def test_skip_processing_empty_manifest(self):
        """Test skip_processing with empty manifest"""
        # Create empty manifest
        empty_manifest = self.test_dir / "empty_manifest.jsonl"
        empty_manifest.write_text("")

        # Run with skip_processing enabled
        stats = convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=empty_manifest,
            output_folder=self.output_dir / "empty",
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify statistics
        self.assertEqual(stats['total'], 0, "Should process 0 entries")
        self.assertEqual(stats['success'], 0, "Should succeed 0 entries")

    def test_skip_processing_nonexistent_manifest(self):
        """Test skip_processing with nonexistent manifest"""
        # Use nonexistent manifest path
        fake_manifest = self.test_dir / "nonexistent.jsonl"

        # Run with skip_processing enabled
        stats = convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=fake_manifest,
            output_folder=self.output_dir / "fake",
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify statistics
        self.assertEqual(stats['total'], 0, "Should process 0 entries")
        self.assertEqual(stats['success'], 0, "Should succeed 0 entries")

    def test_skip_processing_single_file_no_folder(self):
        """Test skip_processing with single file (no parent folder)"""
        # Create manifest with single file entry (no folder)
        single_file_manifest = self.test_dir / "single_manifest.jsonl"
        single_entry = {
            "source": "single_doc.txt",
            "outputs": ["single_doc.txt"],
            "success": True
        }

        with open(single_file_manifest, 'w') as f:
            f.write(json.dumps(single_entry) + "\n")

        # Run with skip_processing enabled
        stats = convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=single_file_manifest,
            output_folder=self.output_dir / "single",
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify statistics
        self.assertEqual(stats['success'], 1, "Should succeed 1 entry")

        # Verify output file created (should use filename as folder)
        output_files = list((self.output_dir / "single").rglob("*.docx"))
        self.assertEqual(len(output_files), 1, "Should create 1 Word doc")

    def test_skip_processing_preserves_folder_structure(self):
        """Test that skip_processing preserves folder structure in output"""
        # Run with skip_processing enabled
        convert_to_word_batch(
            images_folder=self.images_dir,
            transcription_manifest=self.manifest_path,
            output_folder=self.output_dir,
            transcription_folder=self.transcriptions_dir,
            skip_processing=True
        )

        # Verify folder structure preserved
        self.assertTrue((self.output_dir / "folder1").exists(), "folder1 should exist")
        self.assertTrue((self.output_dir / "folder2").exists(), "folder2 should exist")

        # Verify Word files are in correct folders
        self.assertTrue((self.output_dir / "folder1" / "folder1.docx").exists())
        self.assertTrue((self.output_dir / "folder2" / "folder2.docx").exists())


class TestConvertToWordIntegration(unittest.TestCase):
    """Integration tests for convert_to_word with other pipeline components"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir) / "integration"
        self.test_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_skip_processing_with_workflow_manifest_format(self):
        """Test skip_processing with realistic workflow manifest format"""
        # Create manifest matching actual workflow output format
        transcriptions_dir = self.test_dir / "transcriptions"
        output_dir = self.test_dir / "word_output"
        transcriptions_dir.mkdir()
        output_dir.mkdir()

        manifest_path = transcriptions_dir / "transcriptions_manifest.jsonl"

        # Realistic manifest entry from transcribe_qwen_max
        realistic_entries = [
            {
                "source": "Document Set 1/page_001.jpg",
                "outputs": ["Document Set 1/page_001.txt"],
                "processed_at": datetime.now().isoformat(),
                "success": True,
                "details": {"text_length": 1542}
            },
            {
                "source": "Document Set 1/page_002.jpg",
                "outputs": ["Document Set 1/page_002.txt"],
                "processed_at": datetime.now().isoformat(),
                "success": True,
                "details": {"text_length": 1832}
            }
        ]

        with open(manifest_path, 'w') as f:
            for entry in realistic_entries:
                f.write(json.dumps(entry) + "\n")

        # Run skip_processing
        stats = convert_to_word_batch(
            images_folder=self.test_dir / "images",
            transcription_manifest=manifest_path,
            output_folder=output_dir,
            transcription_folder=transcriptions_dir,
            skip_processing=True
        )

        # Verify
        self.assertEqual(stats['success'], 2, "Both entries should succeed")
        self.assertTrue((output_dir / "Document Set 1" / "Document Set 1.docx").exists())


if __name__ == '__main__':
    unittest.main()
