"""
Fixed Unit tests for Library Commands
Tests all the enhanced library functionality with proper mocking
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

class TestLibraryCommands:
    """Test cases for LibraryCommands with proper mocking"""
    
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
        """Create test collection data"""
        from datetime import datetime
        
        # Create test collection
        self.test_collection = Mock(
            id="test-collection-123",
            name="Test Collection",
            type="local",
            source_path="/test/source",
            local_path="/test/local",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata={"description": "Test collection for testing"}
        )
        
        # Add to mock library manager
        self.mock_library_manager.collections.append(self.test_collection)
        
        # Create test collection items
        self.test_items = [
            Mock(id="item-1", name="test1.jpg"),
            Mock(id="item-2", name="test2.jpg")
        ]
        self.mock_library_manager.items["test-collection-123"] = self.test_items
    
    @pytest.mark.asyncio
    async def test_list_collections_success(self):
        """Test successful listing of collections"""
        # Test with existing collection that has a valid path
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
    async def test_list_collections_no_collections(self):
        """Test listing when no collections exist"""
        # Clear collections
        self.mock_library_manager.collections.clear()
        
        await self.library_commands._list_collections()
    
    @pytest.mark.asyncio
    async def test_list_collections_error(self):
        """Test error handling in list collections"""
        # Mock error
        self.mock_library_manager.get_all_collections = AsyncMock(side_effect=Exception("Database error"))
        
        await self.library_commands._list_collections()
    
    @pytest.mark.asyncio
    async def test_list_processing_steps_success(self):
        """Test successful listing of processing steps"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator
            mock_navigator = Mock()
            mock_navigator.get_available_steps.return_value = [
                Mock(name="documents", description="Original documents"),
                Mock(name="rotated", description="Rotated images")
            ]
            mock_navigator.get_step_outputs.return_value = [
                Mock(name="test1.jpg", size=1024),
                Mock(name="test2.jpg", size=2048)
            ]
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            await self.library_commands._list_processing_steps("test-collection-123", True)
    
    @pytest.mark.asyncio
    async def test_list_processing_steps_collection_not_found(self):
        """Test listing steps for non-existent collection"""
        # Mock collection not found
        with pytest.MonkeyPatch().context() as m:
            m.setattr(self.library_commands, "_get_collection_by_id", 
                     AsyncMock(return_value=None))
            
            await self.library_commands._list_processing_steps("nonexistent", False)
    
    @pytest.mark.asyncio
    async def test_view_processing_step_success(self):
        """Test successful viewing of processing step"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator
            mock_navigator = Mock()
            mock_navigator.steps = {
                "documents": Mock(
                    name="documents",
                    description="Original documents",
                    path=Path("documents"),
                    file_types=[".jpg", ".png"]
                )
            }
            mock_navigator.get_step_outputs.return_value = [
                Mock(name="test1.jpg", size=1024, modified="2025-01-01")
            ]
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            await self.library_commands._view_processing_step(
                "test-collection-123", "documents", True, True
            )
    
    @pytest.mark.asyncio
    async def test_search_collection_success(self):
        """Test successful search across processing steps"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator
            mock_navigator = Mock()
            mock_navigator.search_across_steps.return_value = [
                Mock(step="documents", name="test1.jpg", file_type=".jpg", size=1024, path="/test/path")
            ]
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            await self.library_commands._search_collection("test-collection-123", "test", ".jpg")
    
    @pytest.mark.asyncio
    async def test_view_file_success(self):
        """Test successful file viewing"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock ProcessingNavigator
            mock_navigator = Mock()
            mock_navigator.get_step_outputs.return_value = [
                Mock(name="test1.txt", size=1024, modified="2025-01-01", file_type=".txt")
            ]
            mock_navigator.get_file_content_preview.return_value = "This is test content"
            
            m.setattr(ProcessingNavigator, "__new__", lambda cls, path: mock_navigator)
            
            await self.library_commands._view_file(
                "test-collection-123", "transcriptions", "test1.txt", 10
            )
    
    @pytest.mark.asyncio
    async def test_process_collection_success(self):
        """Test successful collection processing"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock successful processing
            self.library_commands.bridge.process_collection = AsyncMock(return_value={
                "success": True,
                "processed_steps": ["documents", "rotated"]
            })
            
            await self.library_commands._process_collection(
                "test-collection-123", "documents,rotated", None
            )
    
    @pytest.mark.asyncio
    async def test_get_processing_status_success(self):
        """Test successful processing status retrieval"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock successful status
            self.library_commands.bridge.get_collection_processing_status = AsyncMock(return_value={
                "collection_path": "/test/path",
                "total_files": 10,
                "available_steps": ["documents", "rotated"],
                "steps_status": {
                    "documents": {"status": "completed", "file_count": 5, "description": "Original docs"},
                    "rotated": {"status": "completed", "file_count": 3, "description": "Rotated images"}
                }
            })
            
            await self.library_commands._get_processing_status("test-collection-123")
    
    @pytest.mark.asyncio
    async def test_preview_structure_success(self):
        """Test successful structure preview"""
        # Mock collection retrieval
        with pytest.MonkeyPatch().context() as m:
            m.setattr(Path, "exists", lambda x: True)
            
            # Mock successful structure
            self.library_commands.bridge.preview_collection_structure = AsyncMock(return_value={
                "collection_path": "/test/path",
                "max_depth": 3,
                "structure": {
                    "type": "directory",
                    "name": "test",
                    "children": [
                        {"type": "file", "name": "test1.jpg", "size": 1024}
                    ]
                }
            })
            
            await self.library_commands._preview_structure("test-collection-123", 3)
    
    @pytest.mark.asyncio
    async def test_get_collection_by_id_success(self):
        """Test successful collection retrieval by ID"""
        result = await self.library_commands._get_collection_by_id("test-collection-123")
        
        assert result == self.test_collection
    
    @pytest.mark.asyncio
    async def test_get_collection_by_id_not_found(self):
        """Test collection retrieval when ID not found"""
        result = await self.library_commands._get_collection_by_id("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_collection_by_id_error(self):
        """Test error handling in collection retrieval"""
        # Mock error
        self.mock_library_manager.get_all_collections = AsyncMock(side_effect=Exception("Database error"))
        
        result = await self.library_commands._get_collection_by_id("test-collection-123")
        
        assert result is None
    
    def test_format_file_size(self):
        """Test file size formatting"""
        # Test bytes
        assert self.library_commands._format_file_size(512) == "512.0 B"
        
        # Test KB
        assert self.library_commands._format_file_size(1536) == "1.5 KB"
        
        # Test MB
        assert self.library_commands._format_file_size(1572864) == "1.5 MB"
        
        # Test GB
        assert self.library_commands._format_file_size(1610612736) == "1.5 GB"
    
    def test_build_tree_display(self):
        """Test tree display building"""
        from rich.tree import Tree
        
        tree = Tree("root")
        
        # Test file
        file_structure = {"type": "file", "name": "test.txt", "size": 1024}
        self.library_commands._build_tree_display(tree, file_structure, 3)
        
        # Test directory
        dir_structure = {
            "type": "directory", 
            "name": "test_dir",
            "children": [{"type": "file", "name": "test.txt", "size": 1024}]
            }
        self.library_commands._build_tree_display(tree, dir_structure, 3)
        
        # Test truncated
        truncated_structure = {"type": "truncated", "depth": 3}
        self.library_commands._build_tree_display(tree, truncated_structure, 3)

    pytest.main([__file__, "-v"])
