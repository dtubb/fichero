"""
Unit tests for ProcessingNavigator
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime

from fichero.library.processing_navigator import ProcessingNavigator, ProcessingStep, ProcessingOutput

class TestProcessingNavigator:
    """Test cases for ProcessingNavigator"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.collection_path = self.temp_dir / "test_collection"
        self.collection_path.mkdir()
        
        # Create test structure
        self._create_test_structure()
        
        self.navigator = ProcessingNavigator(self.collection_path)
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def _create_test_structure(self):
        """Create test directory structure"""
        # Create documents directory
        docs_dir = self.collection_path / "documents"
        docs_dir.mkdir()
        
        # Create test JPG files
        (docs_dir / "test1.jpg").write_text("fake jpg content")
        (docs_dir / "test2.jpg").write_text("fake jpg content")
        
        # Create assets directory structure
        assets_dir = self.collection_path / "assets"
        assets_dir.mkdir()
        
        # Create rotated step
        rotated_dir = assets_dir / "rotated" / "documents"
        rotated_dir.mkdir(parents=True)
        (rotated_dir / "test1_rotated.jpg").write_text("fake rotated jpg")
        
        # Create manifest file
        manifest_file = assets_dir / "rotated" / "rotate_manifest.jsonl"
        manifest_data = [
            {"file": "test1_rotated.jpg", "status": "completed"},
            {"file": "test2_rotated.jpg", "status": "pending"}
        ]
        with open(manifest_file, 'w') as f:
            for entry in manifest_data:
                f.write(json.dumps(entry) + '\n')
        
        # Create transcriptions step
        trans_dir = assets_dir / "transcriptions" / "documents"
        trans_dir.mkdir(parents=True)
        (trans_dir / "test1.txt").write_text("This is a test transcription")
        (trans_dir / "test2.txt").write_text("Another test transcription")
        
        # Create LLM catalogue
        llm_dir = assets_dir / "llm_catalogue"
        llm_dir.mkdir()
        (llm_dir / "summary.json").write_text('{"summary": "Test summary"}')
    
    def test_initialization(self):
        """Test navigator initialization"""
        assert self.navigator.collection_path == self.collection_path
        assert len(self.navigator.steps) == len(ProcessingNavigator.PROCESSING_STEPS)
        assert "documents" in self.navigator.steps
        assert "rotated" in self.navigator.steps
    
    def test_get_available_steps(self):
        """Test getting available processing steps"""
        available_steps = self.navigator.get_available_steps()
        
        # Should have documents, rotated, transcriptions, and llm_catalogue
        step_names = [step.name for step in available_steps]
        assert "documents" in step_names
        assert "rotated" in step_names
        assert "transcriptions" in step_names
        assert "llm_catalogue" in step_names
    
    def test_get_step_outputs(self):
        """Test getting outputs from a processing step"""
        # Test documents step
        outputs = self.navigator.get_step_outputs("documents")
        assert len(outputs) == 2
        assert all(output.step == "documents" for output in outputs)
        assert all(output.file_type == ".jpg" for output in outputs)
        
        # Test rotated step
        outputs = self.navigator.get_step_outputs("rotated")
        assert len(outputs) == 1
        assert outputs[0].name == "test1_rotated.jpg"
        assert outputs[0].step == "rotated"
    
    def test_get_step_manifest(self):
        """Test getting manifest information"""
        manifest = self.navigator.get_step_manifest("rotated")
        
        assert manifest is not None
        assert manifest["count"] == 2
        assert len(manifest["entries"]) == 2
        assert manifest["entries"][0]["file"] == "test1_rotated.jpg"
        assert manifest["entries"][1]["file"] == "test2_rotated.jpg"
    
    def test_search_across_steps(self):
        """Test searching across all processing steps"""
        # Search for "test1"
        results = self.navigator.search_across_steps("test1")
        assert len(results) >= 2  # Should find test1.jpg and test1_rotated.jpg
        
        # Search for specific file type
        results = self.navigator.search_across_steps("test", [".txt"])
        assert len(results) == 2  # Should find test1.txt and test2.txt
        assert all(result.file_type == ".txt" for result in results)
    
    def test_get_file_content_preview(self):
        """Test getting file content preview"""
        # Get a text file output
        outputs = self.navigator.get_step_outputs("transcriptions")
        assert len(outputs) > 0
        
        preview = self.navigator.get_file_content_preview(outputs[0])
        assert preview is not None
        assert "test transcription" in preview
        
        # Test JSON file
        outputs = self.navigator.get_step_outputs("llm_catalogue")
        assert len(outputs) > 0
        
        preview = self.navigator.get_file_content_preview(outputs[0])
        assert preview is not None
        assert "summary" in preview
    
    def test_get_processing_summary(self):
        """Test getting processing summary"""
        summary = self.navigator.get_processing_summary()
        
        assert summary["collection_path"] == str(self.collection_path)
        assert summary["total_files"] > 0
        assert "documents" in summary["available_steps"]
        assert "rotated" in summary["available_steps"]
        
        # Check step details
        assert summary["steps"]["documents"]["file_count"] == 2
        assert summary["steps"]["rotated"]["file_count"] == 1
        assert summary["steps"]["transcriptions"]["file_count"] == 2
    
    def test_unknown_step(self):
        """Test handling of unknown processing steps"""
        outputs = self.navigator.get_step_outputs("unknown_step")
        assert outputs == []
        
        manifest = self.navigator.get_step_manifest("unknown_step")
        assert manifest is None
        
        progress = self.navigator.get_step_progress("unknown_step")
        assert progress is None
    
    def test_empty_collection(self):
        """Test navigator with empty collection"""
        empty_dir = self.temp_dir / "empty_collection"
        empty_dir.mkdir()
        
        empty_navigator = ProcessingNavigator(empty_dir)
        available_steps = empty_navigator.get_available_steps()
        assert len(available_steps) == 0
        
        summary = empty_navigator.get_processing_summary()
        assert summary["total_files"] == 0
        assert len(summary["available_steps"]) == 0

class TestProcessingStep:
    """Test cases for ProcessingStep dataclass"""
    
    def test_processing_step_creation(self):
        """Test creating a ProcessingStep"""
        step = ProcessingStep(
            name="test_step",
            path=Path("test/path"),
            description="Test description",
            file_types=[".txt", ".json"],
            manifest_file="test_manifest.jsonl",
            progress_file="test_progress.jsonl"
        )
        
        assert step.name == "test_step"
        assert step.path == Path("test/path")
        assert step.description == "Test description"
        assert step.file_types == [".txt", ".json"]
        assert step.manifest_file == "test_manifest.jsonl"
        assert step.progress_file == "test_progress.jsonl"

class TestProcessingOutput:
    """Test cases for ProcessingOutput dataclass"""
    
    def test_processing_output_creation(self):
        """Test creating a ProcessingOutput"""
        now = datetime.now()
        output = ProcessingOutput(
            name="test_file.txt",
            path=Path("/test/path/test_file.txt"),
            size=1024,
            modified=now,
            file_type=".txt",
            step="transcriptions"
        )
        
        assert output.name == "test_file.txt"
        assert output.path == Path("/test/path/test_file.txt")
        assert output.size == 1024
        assert output.modified == now
        assert output.file_type == ".txt"
        assert output.step == "transcriptions"
