"""
Unit tests for crop tool library metadata integration

Tests validation, library mode, and standalone mode operation.
"""

import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, MagicMock, patch
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fichero.tools.crop import (
    validate_crop_box,
    process_image,
    DEFAULT_CONTOUR_SETTINGS
)


class TestValidateCropBox:
    """Test crop box validation function"""

    def test_valid_crop_box(self):
        """Test crop box validation with valid coordinates"""
        box = {"x1": 100, "y1": 50, "x2": 800, "y2": 650}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert is_valid
        assert error is None

    def test_negative_coordinates(self):
        """Test crop box validation rejects negative coordinates"""
        box = {"x1": -10, "y1": 50, "x2": 800, "y2": 650}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert not is_valid
        assert "non-negative" in error

    def test_exceeds_bounds_width(self):
        """Test crop box validation rejects out-of-bounds width"""
        box = {"x1": 100, "y1": 50, "x2": 1200, "y2": 650}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert not is_valid
        assert "exceeds image dimensions" in error

    def test_exceeds_bounds_height(self):
        """Test crop box validation rejects out-of-bounds height"""
        box = {"x1": 100, "y1": 50, "x2": 800, "y2": 800}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert not is_valid
        assert "exceeds image dimensions" in error

    def test_zero_width(self):
        """Test crop box validation rejects zero-width boxes"""
        box = {"x1": 100, "y1": 50, "x2": 100, "y2": 650}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert not is_valid
        assert "positive area" in error

    def test_zero_height(self):
        """Test crop box validation rejects zero-height boxes"""
        box = {"x1": 100, "y1": 50, "x2": 800, "y2": 50}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert not is_valid
        assert "positive area" in error

    def test_inverted_coordinates(self):
        """Test crop box validation rejects inverted coordinates"""
        box = {"x1": 800, "y1": 50, "x2": 100, "y2": 650}
        is_valid, error = validate_crop_box(box, 1000, 700)

        assert not is_valid
        assert "positive area" in error


class TestProcessImageStandalone:
    """Test process_image in standalone mode (no library_manager)"""

    @pytest.fixture
    def temp_image(self, tmp_path):
        """Create a temporary test image"""
        img_path = tmp_path / "test.jpg"
        img = Image.new('RGB', (1000, 800), color='white')
        img.save(img_path)
        return img_path

    @pytest.fixture
    def output_path(self, tmp_path):
        """Create output path"""
        return tmp_path / "output" / "test.jpg"

    @patch('fichero.tools.crop.yolo_model', None)  # Disable YOLO for standalone tests
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_process_image_standalone_no_library(self, temp_image, output_path):
        """Test process_image in standalone mode without library_manager"""
        result = process_image(
            file_path=temp_image,
            out_path=output_path,
            output_format='jpg',
            contour_settings=DEFAULT_CONTOUR_SETTINGS
        )

        # Verify result structure
        assert "outputs" in result
        assert "source" in result
        assert "details" in result

        # Verify output file was created
        assert output_path.exists()

        # Verify metadata structure
        details = result["details"]
        assert "method" in details
        assert "confidence" in details
        assert "box" in details
        assert "original_size" in details
        assert "cropped_size" in details
        assert "rotation" in details
        assert "attempts" in details
        assert "output_format" in details

    @patch('fichero.tools.crop.yolo_model', None)
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_process_image_creates_output_directory(self, temp_image, tmp_path):
        """Test that process_image creates output directory if it doesn't exist"""
        output_path = tmp_path / "new_dir" / "subdir" / "test.jpg"

        result = process_image(
            file_path=temp_image,
            out_path=output_path,
            output_format='jpg',
            contour_settings=DEFAULT_CONTOUR_SETTINGS
        )

        assert output_path.exists()
        assert result["outputs"]


class TestProcessImageLibraryMode:
    """Test process_image in library mode (with library_manager)"""

    @pytest.fixture
    def temp_image(self, tmp_path):
        """Create a temporary test image"""
        img_path = tmp_path / "test.jpg"
        img = Image.new('RGB', (1000, 800), color='white')
        img.save(img_path)
        return img_path

    @pytest.fixture
    def output_path(self, tmp_path):
        """Create output path"""
        return tmp_path / "output" / "test.jpg"

    @pytest.fixture
    def mock_library_manager(self):
        """Create a mock library manager"""
        library_manager = Mock()
        metadata_api = Mock()

        # Mock save_step_metadata to return True
        metadata_api.save_step_metadata = Mock(return_value=True)

        library_manager.metadata_api = metadata_api
        return library_manager

    @patch('fichero.tools.crop.yolo_model', None)
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_process_image_library_mode_saves_metadata(
        self, temp_image, output_path, mock_library_manager
    ):
        """Test process_image in library mode saves metadata"""
        result = process_image(
            file_path=temp_image,
            out_path=output_path,
            library_manager=mock_library_manager,
            item_id="test-item-123"
        )

        # Verify result structure (same as standalone)
        assert "outputs" in result
        assert "source" in result
        assert "details" in result

        # Verify library metadata was saved
        assert mock_library_manager.metadata_api.save_step_metadata.called
        call_args = mock_library_manager.metadata_api.save_step_metadata.call_args

        # Verify arguments passed to save_step_metadata
        assert call_args[1]['item_id'] == "test-item-123"
        assert call_args[1]['step_name'] == "crop"
        assert call_args[1]['version'] == 1

        # Verify metadata structure
        metadata = call_args[1]['metadata']
        assert 'method' in metadata
        assert 'confidence' in metadata
        assert 'box' in metadata
        assert 'padding' in metadata
        assert 'output_format' in metadata
        assert 'original_size' in metadata
        assert 'cropped_size' in metadata
        assert 'attempts' in metadata
        assert 'rotation' in metadata
        assert 'input_metadata' in metadata

    @patch('fichero.tools.crop.yolo_model', None)
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_process_image_library_mode_handles_save_failure(
        self, temp_image, output_path, mock_library_manager
    ):
        """Test that processing continues even if metadata save fails"""
        # Make save_step_metadata return False
        mock_library_manager.metadata_api.save_step_metadata.return_value = False

        result = process_image(
            file_path=temp_image,
            out_path=output_path,
            library_manager=mock_library_manager,
            item_id="test-item-123"
        )

        # Processing should still succeed
        assert "outputs" in result
        assert output_path.exists()

        # Metadata save should have been attempted
        assert mock_library_manager.metadata_api.save_step_metadata.called

    @patch('fichero.tools.crop.yolo_model', None)
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_process_image_library_mode_handles_exception(
        self, temp_image, output_path, mock_library_manager
    ):
        """Test that processing continues even if metadata save raises exception"""
        # Make save_step_metadata raise exception
        mock_library_manager.metadata_api.save_step_metadata.side_effect = Exception(
            "Test exception"
        )

        result = process_image(
            file_path=temp_image,
            out_path=output_path,
            library_manager=mock_library_manager,
            item_id="test-item-123"
        )

        # Processing should still succeed
        assert "outputs" in result
        assert output_path.exists()

    @patch('fichero.tools.crop.yolo_model', None)
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_process_image_without_item_id_skips_library_save(
        self, temp_image, output_path, mock_library_manager
    ):
        """Test that library mode requires both library_manager AND item_id"""
        result = process_image(
            file_path=temp_image,
            out_path=output_path,
            library_manager=mock_library_manager
            # item_id not provided
        )

        # Processing should succeed
        assert "outputs" in result

        # But metadata save should NOT have been called
        assert not mock_library_manager.metadata_api.save_step_metadata.called


class TestProcessImageValidation:
    """Test that process_image validates crop boxes"""

    @pytest.fixture
    def temp_image(self, tmp_path):
        """Create a temporary test image"""
        img_path = tmp_path / "test.jpg"
        img = Image.new('RGB', (1000, 800), color='white')
        img.save(img_path)
        return img_path

    @pytest.fixture
    def output_path(self, tmp_path):
        """Create output path"""
        return tmp_path / "output" / "test.jpg"

    @patch('fichero.tools.crop.yolo_model', None)
    @patch('fichero.tools.crop.YOLO_AVAILABLE', False)
    def test_invalid_crop_box_falls_back_to_original(
        self, temp_image, output_path, monkeypatch
    ):
        """Test that invalid crop box triggers fallback to original image"""

        # Mock crop_with_contours to return an invalid crop box
        def mock_crop_with_contours(*args, **kwargs):
            from fichero.tools.crop import create_crop_info
            from PIL import Image

            # Return crop box that exceeds image bounds
            invalid_crop_info = create_crop_info(
                box={"x1": 100, "y1": 50, "x2": 2000, "y2": 1000},  # x2 exceeds bounds
                method="contour",
                confidence=1.0,
                padding=30,
                original_size=[1000, 800],
                cropped_size=[1900, 950],
                rotation={"reason": "No EXIF rotation needed"}
            )

            # Return a dummy image
            img = Image.new('RGB', (1900, 950), color='white')
            return (img, invalid_crop_info)

        # Patch crop_with_contours
        monkeypatch.setattr('fichero.tools.crop.crop_with_contours', mock_crop_with_contours)

        result = process_image(
            file_path=temp_image,
            out_path=output_path
        )

        # Should fall back to original method
        assert result["details"]["method"] == "original"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
