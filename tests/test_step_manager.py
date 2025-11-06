"""
Unit tests for StepManager (PHASE 4)

Tests state management, navigation, and event system.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock

from fichero.windows.main.views.output.step_manager import StepManager, Step, StepState


class TestStepManager:
    """Test StepManager functionality"""

    @pytest.fixture
    def mock_library_manager(self):
        """Create mock library manager"""
        manager = Mock()
        manager.get_item_output_data = AsyncMock()
        return manager

    @pytest.fixture
    def step_manager(self, mock_library_manager):
        """Create StepManager instance"""
        return StepManager(mock_library_manager)

    @pytest.fixture
    def sample_output_data(self):
        """Sample output data from library"""
        step1 = Mock()
        step1.step_name = "Crop Image"
        step1.step_number = 1
        step1.file_path = Path("/tmp/step1.jpg")
        step1.file_type = "image"
        step1.description = "Cropped image"

        step2 = Mock()
        step2.step_name = "Enhance"
        step2.step_number = 2
        step2.file_path = Path("/tmp/step2.jpg")
        step2.file_type = "image"
        step2.description = "Enhanced image"

        step3 = Mock()
        step3.step_name = "Transcribe"
        step3.step_number = 3
        step3.file_path = Path("/tmp/step3.txt")
        step3.file_type = "text"
        step3.description = "Transcribed text"

        return {
            'processing_steps': [step1, step2, step3],
            'is_folder': False,
            'output_path': '/tmp/output.json'
        }

    # ==================== INITIALIZATION TESTS ====================

    def test_init_requires_library_manager(self):
        """Test that library_manager is required"""
        with pytest.raises(ValueError, match="library_manager is required"):
            StepManager(None)

    def test_init_sets_defaults(self, step_manager):
        """Test initialization sets default values"""
        assert step_manager.current_item_id is None
        assert step_manager.steps == []
        assert step_manager.current_step_index == 0
        assert step_manager.item_ids == []
        assert step_manager.current_file_index == 0
        assert step_manager.is_folder is False

    # ==================== LOAD ITEM TESTS ====================

    @pytest.mark.asyncio
    async def test_load_item_success(self, step_manager, mock_library_manager, sample_output_data):
        """Test successfully loading item steps"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data

        result = await step_manager.load_item("item-123")

        assert result is True
        assert step_manager.current_item_id == "item-123"
        assert len(step_manager.steps) == 3
        assert step_manager.steps[0].step_name == "Crop Image"
        assert step_manager.steps[1].step_name == "Enhance"
        assert step_manager.steps[2].step_name == "Transcribe"

    @pytest.mark.asyncio
    async def test_load_item_no_steps(self, step_manager, mock_library_manager):
        """Test loading item with no processing steps"""
        mock_library_manager.get_item_output_data.return_value = {
            'processing_steps': [],
            'is_folder': False
        }

        result = await step_manager.load_item("item-123")

        assert result is False
        assert step_manager.steps == []

    @pytest.mark.asyncio
    async def test_load_item_none_output_data(self, step_manager, mock_library_manager):
        """Test loading item with no output data"""
        mock_library_manager.get_item_output_data.return_value = None

        result = await step_manager.load_item("item-123")

        assert result is False
        assert step_manager.steps == []

    # ==================== NAVIGATION TESTS ====================

    @pytest.mark.asyncio
    async def test_next_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test navigating to next step"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")

        assert step_manager.current_step_index == 0
        assert step_manager.next_step() is True
        assert step_manager.current_step_index == 1
        assert step_manager.next_step() is True
        assert step_manager.current_step_index == 2
        assert step_manager.next_step() is False  # At end
        assert step_manager.current_step_index == 2

    @pytest.mark.asyncio
    async def test_prev_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test navigating to previous step"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")
        step_manager.current_step_index = 2

        assert step_manager.prev_step() is True
        assert step_manager.current_step_index == 1
        assert step_manager.prev_step() is True
        assert step_manager.current_step_index == 0
        assert step_manager.prev_step() is False  # At beginning
        assert step_manager.current_step_index == 0

    @pytest.mark.asyncio
    async def test_has_next_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test has_next_step detection"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")

        assert step_manager.has_next_step() is True
        step_manager.current_step_index = 1
        assert step_manager.has_next_step() is True
        step_manager.current_step_index = 2
        assert step_manager.has_next_step() is False

    @pytest.mark.asyncio
    async def test_has_prev_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test has_prev_step detection"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")

        assert step_manager.has_prev_step() is False
        step_manager.current_step_index = 1
        assert step_manager.has_prev_step() is True
        step_manager.current_step_index = 2
        assert step_manager.has_prev_step() is True

    # ==================== STATE TESTS ====================

    @pytest.mark.asyncio
    async def test_get_state(self, step_manager, mock_library_manager, sample_output_data):
        """Test get_state returns correct StepState"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")
        step_manager.current_step_index = 1

        state = step_manager.get_state()

        assert isinstance(state, StepState)
        assert state.item_id == "item-123"
        assert state.step_index == 1
        assert state.total_steps == 3
        assert state.file_index == 0
        assert state.total_files == 0
        assert state.can_go_prev_step is True
        assert state.can_go_next_step is True
        assert state.can_go_prev_file is False
        assert state.can_go_next_file is False

    # ==================== EVENT SYSTEM TESTS ====================

    @pytest.mark.asyncio
    async def test_state_change_event_on_next_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test state change event fires on next_step"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")

        callback = Mock()
        step_manager.on_state_changed = callback

        step_manager.next_step()

        assert callback.called
        state = callback.call_args[0][0]
        assert state.step_index == 1

    @pytest.mark.asyncio
    async def test_state_change_event_on_prev_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test state change event fires on prev_step"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")
        step_manager.current_step_index = 1

        callback = Mock()
        step_manager.on_state_changed = callback

        step_manager.prev_step()

        assert callback.called
        state = callback.call_args[0][0]
        assert state.step_index == 0

    @pytest.mark.asyncio
    async def test_state_change_event_on_set_current_step(self, step_manager, mock_library_manager, sample_output_data):
        """Test state change event fires on set_current_step"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")

        callback = Mock()
        step_manager.on_state_changed = callback

        step_manager.set_current_step(2)

        assert callback.called
        state = callback.call_args[0][0]
        assert state.step_index == 2

    # ==================== MULTI-ITEM NAVIGATION TESTS ====================

    @pytest.mark.asyncio
    async def test_load_item_list(self, step_manager, mock_library_manager, sample_output_data):
        """Test loading a list of items"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data

        await step_manager.load_item_list(['item-1', 'item-2', 'item-3'], initial_index=0)

        assert step_manager.item_ids == ['item-1', 'item-2', 'item-3']
        assert step_manager.current_file_index == 0
        assert step_manager.current_item_id == 'item-1'

    @pytest.mark.asyncio
    async def test_next_file(self, step_manager, mock_library_manager, sample_output_data):
        """Test navigating to next file"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item_list(['item-1', 'item-2', 'item-3'])

        result = await step_manager.next_file()

        assert result is True
        assert step_manager.current_file_index == 1
        assert step_manager.current_item_id == 'item-2'

    @pytest.mark.asyncio
    async def test_prev_file(self, step_manager, mock_library_manager, sample_output_data):
        """Test navigating to previous file"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item_list(['item-1', 'item-2', 'item-3'], initial_index=1)

        result = await step_manager.prev_file()

        assert result is True
        assert step_manager.current_file_index == 0
        assert step_manager.current_item_id == 'item-1'

    @pytest.mark.asyncio
    async def test_go_to_file(self, step_manager, mock_library_manager, sample_output_data):
        """Test jumping to specific file"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item_list(['item-1', 'item-2', 'item-3'])

        result = await step_manager.go_to_file(2)

        assert result is True
        assert step_manager.current_file_index == 2
        assert step_manager.current_item_id == 'item-3'

    # ==================== GET CURRENT STEP DATA TESTS ====================

    @pytest.mark.asyncio
    async def test_get_current_step_data(self, step_manager, mock_library_manager, sample_output_data):
        """Test getting current step data"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")
        step_manager.current_step_index = 1

        data = await step_manager.get_current_step_data()

        assert data is not None
        assert data['item_id'] == "item-123"
        assert data['step_index'] == 1
        assert data['step_name'] == "Enhance"
        assert data['file_type'] == "image"
        assert 'output_data' in data

    @pytest.mark.asyncio
    async def test_get_current_step_data_no_item(self, step_manager):
        """Test getting current step data with no loaded item"""
        data = await step_manager.get_current_step_data()
        assert data is None

    # ==================== CLEAR TESTS ====================

    @pytest.mark.asyncio
    async def test_clear(self, step_manager, mock_library_manager, sample_output_data):
        """Test clearing step manager state"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data
        await step_manager.load_item("item-123")
        step_manager.current_step_index = 2

        step_manager.clear()

        assert step_manager.steps == []
        assert step_manager.current_step_index == 0
        assert step_manager.current_item_id is None
        assert step_manager.is_folder is False
        # item_ids should be preserved
        assert step_manager.item_ids == []
