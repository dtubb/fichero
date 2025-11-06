"""
Unit tests for OutputPane (PHASE 4)

Tests display, zoom, rotation, and state management.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from fichero.windows.main.views.output.output_pane import OutputPane


class TestOutputPane:
    """Test OutputPane functionality"""

    @pytest.fixture
    def mock_library_manager(self):
        """Create mock library manager"""
        manager = Mock()
        manager.get_item_output_data = AsyncMock()
        return manager

    @pytest.fixture
    def mock_renderer_registry(self):
        """Create mock renderer registry"""
        return Mock()

    @pytest.fixture
    def mock_toga_components(self):
        """Mock Toga components"""
        with patch('fichero.windows.main.views.output.output_pane.toga.Box') as mock_box, \
             patch('fichero.windows.main.views.output.output_pane.toga.Label') as mock_label, \
             patch('fichero.windows.main.views.output.output_pane.toga.WebView') as mock_webview:

            # Setup mock instances
            mock_box_instance = MagicMock()
            mock_box.return_value = mock_box_instance

            mock_label_instance = MagicMock()
            mock_label.return_value = mock_label_instance

            mock_webview_instance = MagicMock()
            mock_webview_instance.set_content = Mock()
            mock_webview_instance.evaluate_javascript = Mock()
            mock_webview.return_value = mock_webview_instance

            yield {
                'box': mock_box,
                'label': mock_label,
                'webview': mock_webview,
                'box_instance': mock_box_instance,
                'label_instance': mock_label_instance,
                'webview_instance': mock_webview_instance
            }

    @pytest.fixture
    def output_pane(self, mock_library_manager, mock_renderer_registry, mock_toga_components):
        """Create OutputPane instance"""
        return OutputPane(mock_library_manager, mock_renderer_registry)

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

        return {
            'processing_steps': [step1, step2],
            'is_folder': False,
            'output_path': '/tmp/output.json'
        }

    # ==================== INITIALIZATION TESTS ====================

    def test_init_sets_defaults(self, output_pane):
        """Test initialization sets default values"""
        assert output_pane.library_manager is not None
        assert output_pane.renderer_registry is not None
        assert output_pane.current_item_id is None
        assert output_pane.current_step_index is None
        assert output_pane.scale == 1.0
        assert output_pane.rotation == 0
        assert output_pane.scroll_x == 0
        assert output_pane.scroll_y == 0

    def test_init_creates_ui_components(self, output_pane):
        """Test initialization creates UI components"""
        assert output_pane._container is not None
        assert output_pane._webview is not None
        assert output_pane._loading_label is not None
        assert output_pane._error_label is not None

    # ==================== SET STEP TESTS ====================

    @pytest.mark.asyncio
    async def test_set_step_success(self, output_pane, mock_library_manager, sample_output_data, mock_toga_components):
        """Test successfully setting a step"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data

        await output_pane.set_step("item-123", 0)

        assert output_pane.current_item_id == "item-123"
        assert output_pane.current_step_index == 0
        mock_library_manager.get_item_output_data.assert_called_once_with("item-123")

    @pytest.mark.asyncio
    async def test_set_step_no_output_data(self, output_pane, mock_library_manager):
        """Test setting step with no output data"""
        mock_library_manager.get_item_output_data.return_value = None

        await output_pane.set_step("item-123", 0)

        # Should handle gracefully
        assert output_pane.current_item_id == "item-123"
        assert output_pane.current_step_index == 0

    @pytest.mark.asyncio
    async def test_set_step_no_processing_steps(self, output_pane, mock_library_manager):
        """Test setting step with no processing steps"""
        mock_library_manager.get_item_output_data.return_value = {
            'processing_steps': [],
            'is_folder': False
        }

        await output_pane.set_step("item-123", 0)

        # Should handle gracefully
        assert output_pane.current_item_id == "item-123"

    @pytest.mark.asyncio
    async def test_set_step_out_of_range(self, output_pane, mock_library_manager, sample_output_data):
        """Test setting step with index out of range"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data

        await output_pane.set_step("item-123", 10)

        # Should handle gracefully
        assert output_pane.current_item_id == "item-123"
        assert output_pane.current_step_index == 10

    @pytest.mark.asyncio
    async def test_set_step_renders_html(self, output_pane, mock_library_manager, sample_output_data, mock_toga_components):
        """Test that set_step renders HTML content"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data

        await output_pane.set_step("item-123", 0)

        # WebView should have content set
        webview = mock_toga_components['webview_instance']
        webview.set_content.assert_called_once()

    # ==================== ZOOM TESTS ====================

    def test_zoom_in(self, output_pane):
        """Test zoom in"""
        initial_scale = output_pane.scale
        output_pane.zoom_in()

        assert output_pane.scale == initial_scale + 0.1

    def test_zoom_in_max_limit(self, output_pane):
        """Test zoom in respects maximum limit"""
        output_pane.scale = 5.0
        output_pane.zoom_in()

        assert output_pane.scale == 5.0  # Should not exceed max

    def test_zoom_out(self, output_pane):
        """Test zoom out"""
        output_pane.scale = 1.5
        output_pane.zoom_out()

        assert output_pane.scale == 1.4

    def test_zoom_out_min_limit(self, output_pane):
        """Test zoom out respects minimum limit"""
        output_pane.scale = 0.1
        output_pane.zoom_out()

        assert output_pane.scale == 0.1  # Should not go below min

    def test_zoom_fit(self, output_pane):
        """Test zoom fit"""
        output_pane.scale = 2.5
        output_pane.zoom_fit()

        # Currently resets to 1.0 (TODO: proper fit calculation)
        assert output_pane.scale == 1.0

    def test_zoom_100(self, output_pane):
        """Test zoom 100%"""
        output_pane.scale = 2.5
        output_pane.zoom_100()

        assert output_pane.scale == 1.0

    def test_zoom_fit_width(self, output_pane):
        """Test zoom fit width"""
        output_pane.scale = 2.5
        output_pane.zoom_fit_width()

        # Currently resets to 1.0 (TODO: proper fit calculation)
        assert output_pane.scale == 1.0

    # ==================== ROTATION TESTS ====================

    def test_rotate_left(self, output_pane):
        """Test rotate left"""
        output_pane.rotation = 90
        output_pane.rotate_left()

        assert output_pane.rotation == 0

    def test_rotate_left_wraps(self, output_pane):
        """Test rotate left wraps around 360°"""
        output_pane.rotation = 0
        output_pane.rotate_left()

        assert output_pane.rotation == 270

    def test_rotate_right(self, output_pane):
        """Test rotate right"""
        output_pane.rotation = 0
        output_pane.rotate_right()

        assert output_pane.rotation == 90

    def test_rotate_right_wraps(self, output_pane):
        """Test rotate right wraps around 360°"""
        output_pane.rotation = 270
        output_pane.rotate_right()

        assert output_pane.rotation == 0

    def test_reset_rotation(self, output_pane):
        """Test reset rotation"""
        output_pane.rotation = 180
        output_pane.reset_rotation()

        assert output_pane.rotation == 0

    # ==================== VIEWER STATE TESTS ====================

    def test_get_viewer_state(self, output_pane):
        """Test getting viewer state"""
        output_pane.scale = 1.5
        output_pane.rotation = 90
        output_pane.scroll_x = 100
        output_pane.scroll_y = 200

        state = output_pane.get_viewer_state()

        assert state['scale'] == 1.5
        assert state['rotation'] == 90
        assert state['scroll_x'] == 100
        assert state['scroll_y'] == 200

    def test_set_viewer_state(self, output_pane, mock_toga_components):
        """Test setting viewer state"""
        state = {
            'scale': 2.0,
            'rotation': 180,
            'scroll_x': 50,
            'scroll_y': 75
        }

        output_pane.set_viewer_state(state)

        assert output_pane.scale == 2.0
        assert output_pane.rotation == 180
        assert output_pane.scroll_x == 50
        assert output_pane.scroll_y == 75

    def test_apply_viewer_state(self, output_pane, mock_toga_components):
        """Test applying viewer state to WebView"""
        output_pane.scale = 1.5
        output_pane.rotation = 90
        output_pane.scroll_x = 100
        output_pane.scroll_y = 200

        output_pane._apply_viewer_state()

        # Should call evaluate_javascript on WebView
        webview = mock_toga_components['webview_instance']
        webview.evaluate_javascript.assert_called()

    # ==================== DISPLAY STATE TESTS ====================

    def test_show_loading(self, output_pane, mock_toga_components):
        """Test showing loading state"""
        container = mock_toga_components['box_instance']

        output_pane._show_loading()

        # Container should be cleared and loading label added
        container.clear.assert_called()
        container.add.assert_called()

    def test_show_error(self, output_pane, mock_toga_components):
        """Test showing error state"""
        container = mock_toga_components['box_instance']

        output_pane._show_error("Test error")

        # Container should be cleared and error label added
        container.clear.assert_called()
        container.add.assert_called()

    def test_show_content(self, output_pane, mock_toga_components):
        """Test showing content state"""
        container = mock_toga_components['box_instance']

        output_pane._show_content()

        # Container should be cleared and webview added
        container.clear.assert_called()
        container.add.assert_called()

    # ==================== AS_BOX TESTS ====================

    def test_as_box(self, output_pane):
        """Test getting container for embedding"""
        box = output_pane.as_box()

        assert box is not None
        assert box == output_pane._container

    # ==================== CLEAR TESTS ====================

    def test_clear(self, output_pane):
        """Test clearing pane content"""
        output_pane.current_item_id = "item-123"
        output_pane.current_step_index = 2

        output_pane.clear()

        assert output_pane.current_item_id is None
        assert output_pane.current_step_index is None

    # ==================== REFRESH TESTS ====================

    @pytest.mark.asyncio
    async def test_refresh_with_content(self, output_pane, mock_library_manager, sample_output_data):
        """Test refreshing current content"""
        mock_library_manager.get_item_output_data.return_value = sample_output_data

        # Set up initial state
        output_pane.current_item_id = "item-123"
        output_pane.current_step_index = 1

        # Refresh should re-render
        output_pane.refresh()

        # Note: refresh() uses asyncio.create_task, so we can't easily test completion
        # Just verify state is still set
        assert output_pane.current_item_id == "item-123"
        assert output_pane.current_step_index == 1

    def test_refresh_without_content(self, output_pane):
        """Test refreshing with no current content"""
        output_pane.current_item_id = None
        output_pane.current_step_index = None

        # Should not raise error
        output_pane.refresh()

    # ==================== RENDER HTML TESTS ====================

    def test_render_step_html_image(self, output_pane, sample_output_data):
        """Test rendering HTML for image step"""
        step = sample_output_data['processing_steps'][0]

        html = output_pane._render_step_html(step, sample_output_data)

        assert "Crop Image" in html
        assert "image" in html.lower()
        assert "<!DOCTYPE html>" in html

    def test_render_step_html_text(self, output_pane):
        """Test rendering HTML for text step"""
        step = Mock()
        step.step_name = "Transcribe"
        step.file_path = Path("/tmp/step.txt")
        step.file_type = "text"
        step.description = "Transcribed text"

        output_data = {
            'processing_steps': [step],
            'output_path': '/tmp/output.json'
        }

        html = output_pane._render_step_html(step, output_data)

        assert "Transcribe" in html
        assert "text" in html.lower()
        assert "<!DOCTYPE html>" in html

    def test_render_step_html_handles_missing_description(self, output_pane):
        """Test rendering HTML when description is missing"""
        step = Mock()
        step.step_name = "Test Step"
        step.file_path = Path("/tmp/step.jpg")
        step.file_type = "image"
        step.description = None

        output_data = {
            'processing_steps': [step],
            'output_path': '/tmp/output.json'
        }

        html = output_pane._render_step_html(step, output_data)

        assert "Test Step" in html
        assert "<!DOCTYPE html>" in html
