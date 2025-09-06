"""
Comprehensive Unit Tests for Library Commands
Tests all the enhanced library functionality comprehensively
"""

import pytest
import tempfile
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock

from fichero.cli.commands.library_commands import LibraryCommands
from fichero.library.processing_navigator import ProcessingNavigator, ProcessingOutput
from fichero.library.director_bridge import LibraryDirectorBridge

class MockLibraryManager:
    """Mock library manager for testing"""
    
    def __init__(self):
        self.collections = []
        self.items = {}
    
    async def get_all_collections(self):
        return self.collections
    
    async def get_collection_items(self, collection_id):
        return self.items.get(collection_id, [])
    
    async def add_collection(self, **kwargs):
        collection_id = f"collection-{len(self.collections) + 1}"
        collection = Mock(
            id=collection_id,
            name=kwargs.get('name', 'Test Collection'),
            type=kwargs.get('collection_type', 'local'),
            source_path=kwargs.get('source_path'),
            local_path=kwargs.get('source_path'),  # Use source_path as local_path for testing
            metadata=kwargs.get('metadata', {})
        )
        self.collections.append(collection)
        return collection_id

class TestLibraryCommandsComprehensive:
    """Comprehensive test cases for LibraryCommands"""
    
    def setup_method(self):
        """Set up test environment"""
        # Create mock app initializer
        self.mock_app_initializer = Mock()
        
        # Create mock library manager
        self.mock_library_manager = MockLibraryManager()
        
        # Mock the library_manager attribute
        self.mock_app_initializer.library_manager = self.mock_library_manager
        
        # Create library commands instance
        self.library_commands = LibraryCommands(self.mock_app_initializer)
        
        # Create test data
        self._create_test_data()
    
    def _create_test_data(self):
        """Create comprehensive test collection data"""
        from datetime import datetime
        
        # Create multiple test collections
        self.test_collections = [
            Mock(
                id="test-collection-1",
                name="Test Collection 1",
                type="local",
                source_path="/test/source1",
                local_path="/test/local1",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                metadata={"description": "First test collection"}
            ),
            Mock(
                id="test-collection-2", 
                name="Test Collection 2",
                type="remote",
                source_path="/test/source2",
                local_path="/test/local2",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                metadata={"description": "Second test collection"}
            )
        ]
        
        # Add to mock library manager
        for collection in self.test_collections:
            self.mock_library_manager.collections.append(collection)
        
        # Create test collection items
        self.test_items = {
            "test-collection-1": [
                Mock(id="item-1", name="test1.jpg"),
                Mock(id="item-2", name="test2.jpg")
            ],
            "test-collection-2": [
                Mock(id="item-3", name="test3.pdf"),
                Mock(id="item-4", name="test4.png")
            ]
        }
        
        for collection_id, items in self.test_items.items():
            self.mock_library_manager.items[collection_id] = items
    
    @pytest.mark.asyncio
    async def test_list_collections_multiple(self):
        """Test listing multiple collections"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            m.setattr(ProcessingNavigator, "get_processing_summary", lambda x: {
                "available_steps": ["documents", "rotated"],
                "steps": {
                    "documents": {"file_count": 5},
                    "rotated": {"file_count": 3}
                }
            })
            
            await self.library_commands._list_collections()
    
    @pytest.mark.asyncio
    async def test_list_collections_with_processing_status(self):
        """Test listing collections with processing status"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            m.setattr(ProcessingNavigator, "get_processing_summary", lambda x: {
                "available_steps": ["documents", "enhanced", "transcriptions"],
                "steps": {
                    "documents": {"file_count": 10, "status": "completed"},
                    "enhanced": {"file_count": 8, "status": "completed"},
                    "transcriptions": {"file_count": 6, "status": "in_progress"}
                }
            })
            
            await self.library_commands._list_collections()
    
    @pytest.mark.asyncio
    async def test_list_processing_steps_comprehensive(self):
        """Test comprehensive listing of processing steps"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator with all steps
            mock_navigator = Mock()
            mock_navigator.get_available_steps.return_value = [
                Mock(name="documents", description="Original documents"),
                Mock(name="rotated", description="Rotated images"),
                Mock(name="crops", description="Cropped images"),
                Mock(name="background_removed", description="Background removed"),
                Mock(name="enhanced", description="Enhanced images"),
                Mock(name="splits", description="Split images"),
                Mock(name="segments", description="Segmented images"),
                Mock(name="transcriptions", description="OCR transcriptions"),
                Mock(name="llm_catalogue", description="LLM processing results")
            ]
            mock_navigator.get_step_outputs.return_value = [
                Mock(name="test1.jpg", size=1024),
                Mock(name="test2.jpg", size=2048)
            ]
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            await self.library_commands._list_processing_steps("test-collection-1", True)
    
    @pytest.mark.asyncio
    async def test_view_processing_step_with_files(self):
        """Test viewing processing step with file details"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator
            mock_navigator = Mock()
            mock_navigator.steps = {
                "documents": Mock(
                    name="documents",
                    description="Original documents",
                    path=Path("documents"),
                    file_types=[".jpg", ".png", ".pdf"]
                )
            }
            mock_navigator.get_step_outputs.return_value = [
                Mock(name="test1.jpg", size=1024, modified="2025-01-01"),
                Mock(name="test2.png", size=2048, modified="2025-01-02"),
                Mock(name="test3.pdf", size=5120, modified="2025-01-03")
            ]
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            await self.library_commands._view_processing_step(
                "test-collection-1", "documents", True, True
            )
    
    @pytest.mark.asyncio
    async def test_search_collection_across_all_steps(self):
        """Test comprehensive search across all processing steps"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator with search results
            mock_navigator = Mock()
            mock_navigator.search_across_steps.return_value = [
                Mock(step="documents", name="test1.jpg", file_type=".jpg", size=1024, path="/test/path1"),
                Mock(step="rotated", name="test1_rotated.jpg", file_type=".jpg", size=1024, path="/test/path2"),
                Mock(step="enhanced", name="test1_enhanced.jpg", file_type=".jpg", size=2048, path="/test/path3"),
                Mock(step="transcriptions", name="test1.txt", file_type=".txt", size=512, path="/test/path4")
            ]
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            # Test search with different file types
            await self.library_commands._search_collection("test-collection-1", "test", ".jpg")
            await self.library_commands._search_collection("test-collection-1", "test", ".txt")
            await self.library_commands._search_collection("test-collection-1", "test", None)
    
    @pytest.mark.asyncio
    async def test_view_file_different_types(self):
        """Test viewing different file types"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator
            mock_navigator = Mock()
            mock_navigator.get_step_outputs.return_value = [
                Mock(name="test1.txt", size=1024, modified="2025-01-01", file_type=".txt"),
                Mock(name="test1.json", size=2048, modified="2025-01-02", file_type=".json")
            ]
            mock_navigator.get_file_content_preview.return_value = "This is test content"
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            # Test viewing text file
            await self.library_commands._view_file(
                "test-collection-1", "transcriptions", "test1.txt", 10
            )
            
            # Test viewing JSON file
            await self.library_commands._view_file(
                "test-collection-1", "llm_catalogue", "test1.json", 20
            )
    
    @pytest.mark.asyncio
    async def test_process_collection_comprehensive(self):
        """Test comprehensive collection processing"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock successful processing with multiple steps
            self.library_commands.bridge.process_collection = AsyncMock(return_value={
                "success": True,
                "processed_steps": ["documents", "rotated", "enhanced", "transcriptions"],
                "total_files": 25,
                "processing_time": "2m 30s"
            })
            
            # Test processing specific steps
            await self.library_commands._process_collection(
                "test-collection-1", "documents,rotated,enhanced", None
            )
            
            # Test processing all steps
            await self.library_commands._process_collection(
                "test-collection-1", "all", None
            )
    
    @pytest.mark.asyncio
    async def test_get_processing_status_comprehensive(self):
        """Test comprehensive processing status retrieval"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock comprehensive status
            self.library_commands.bridge.get_collection_processing_status = AsyncMock(return_value={
                "collection_path": "/test/path",
                "total_files": 25,
                "available_steps": ["documents", "rotated", "enhanced", "transcriptions", "llm_catalogue"],
                "steps_status": {
                    "documents": {"status": "completed", "file_count": 10, "description": "Original docs"},
                    "rotated": {"status": "completed", "file_count": 8, "description": "Rotated images"},
                    "enhanced": {"status": "completed", "file_count": 6, "description": "Enhanced images"},
                    "transcriptions": {"status": "in_progress", "file_count": 4, "description": "OCR processing"},
                    "llm_catalogue": {"status": "pending", "file_count": 0, "description": "LLM analysis"}
                },
                "overall_progress": 72.0,
                "estimated_completion": "15 minutes"
            })
            
            await self.library_commands._get_processing_status("test-collection-1")
    
    @pytest.mark.asyncio
    async def test_preview_structure_comprehensive(self):
        """Test comprehensive structure preview"""
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock comprehensive structure
            self.library_commands.bridge.preview_collection_structure = AsyncMock(return_value={
                "collection_path": "/test/path",
                "max_depth": 5,
                "total_items": 150,
                "structure": {
                    "type": "directory",
                    "name": "test_collection",
                    "size": 0,
                    "children": [
                        {
                            "type": "directory",
                            "name": "documents",
                            "size": 0,
                            "children": [
                                {"type": "file", "name": "test1.jpg", "size": 1024},
                                {"type": "file", "name": "test2.jpg", "size": 2048}
                            ]
                        },
                        {
                            "type": "directory", 
                            "name": "assets",
                            "size": 0,
                            "children": [
                                {
                                    "type": "directory",
                                    "name": "rotated",
                                    "size": 0,
                                    "children": [
                                        {"type": "file", "name": "test1_rotated.jpg", "size": 1024}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            })
            
            # Test different depth levels
            await self.library_commands._preview_structure("test-collection-1", 2)
            await self.library_commands._preview_structure("test-collection-1", 5)
    
    @pytest.mark.asyncio
    async def test_get_collection_by_id_multiple(self):
        """Test collection retrieval for multiple collections"""
        # Test first collection
        result1 = await self.library_commands._get_collection_by_id("test-collection-1")
        assert result1 == self.test_collections[0]
        
        # Test second collection
        result2 = await self.library_commands._get_collection_by_id("test-collection-2")
        assert result2 == self.test_collections[1]
        
        # Test non-existent collection
        result3 = await self.library_commands._get_collection_by_id("nonexistent")
        assert result3 is None
    
    def test_format_file_size_comprehensive(self):
        """Test comprehensive file size formatting"""
        # Test all size ranges
        assert self.library_commands._format_file_size(512) == "512.0 B"
        assert self.library_commands._format_file_size(1536) == "1.5 KB"
        assert self.library_commands._format_file_size(1572864) == "1.5 MB"
        assert self.library_commands._format_file_size(1610612736) == "1.5 GB"
        assert self.library_commands._format_file_size(1649267441664) == "1.5 TB"
        
        # Test edge cases
        assert self.library_commands._format_file_size(0) == "0.0 B"
        assert self.library_commands._format_file_size(1) == "1.0 B"
        assert self.library_commands._format_file_size(1023) == "1023.0 B"
        assert self.library_commands._format_file_size(1024) == "1.0 KB"
    
    def test_build_tree_display_comprehensive(self):
        """Test comprehensive tree display building"""
        from rich.tree import Tree
        
        tree = Tree("root")
        
        # Test file
        file_structure = {"type": "file", "name": "test.txt", "size": 1024}
        self.library_commands._build_tree_display(tree, file_structure, 3)
        
        # Test directory with children
        dir_structure = {
            "type": "directory", 
            "name": "test_dir",
            "size": 0,
            "children": [
                {"type": "file", "name": "test.txt", "size": 1024},
                {"type": "directory", "name": "subdir", "size": 0, "children": []}
            ]
        }
        self.library_commands._build_tree_display(tree, dir_structure, 3)
        
        # Test truncated
        truncated_structure = {"type": "truncated", "depth": 3}
        self.library_commands._build_tree_display(tree, truncated_structure, 3)
        
        # Test unknown type
        unknown_structure = {"type": "unknown", "name": "test"}
        self.library_commands._build_tree_display(tree, unknown_structure, 3)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
