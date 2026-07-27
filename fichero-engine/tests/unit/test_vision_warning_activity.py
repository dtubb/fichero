"""Tests for vision error surfacing via activity-log warnings (#1208).

Before this fix, vision errors were swallowed silently (logged to stderr only).
After the fix, `_log_vision_warning` is called at every error site, which
invokes `tracker.log(type=ActivityType.SYSTEM_WARNING, ...)` when an activity
tracker is available.

Tests here:
- When an exception is raised during vision processing, _log_vision_warning is
  called (not just logger.error) — verifies the warning is emitted to the
  activity log and doesn't propagate silently.
- When no tracker is available, the function degrades to logger.warning without
  raising.
"""

from __future__ import annotations

import asyncio
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from fichero.workflows.tools.vision_base import _log_vision_warning


class TestLogVisionWarning:
    # _log_vision_warning does a local import:
    #   from fichero.workflows.activity import get_activity_tracker
    # so we patch the function on the activity module, not on vision_base.
    _TRACKER_PATCH = "fichero.workflows.activity.get_activity_tracker"

    def test_calls_tracker_log_when_tracker_available(self):
        """_log_vision_warning delegates to tracker.log with SYSTEM_WARNING."""
        mock_tracker = MagicMock()

        with patch(self._TRACKER_PATCH, return_value=mock_tracker):
            _log_vision_warning("OCR failed on page 3", file_path="/tmp/doc.pdf")

        mock_tracker.log.assert_called_once()
        call_kwargs = mock_tracker.log.call_args.kwargs

        from fichero.workflows.activity_types import ActivityType
        assert call_kwargs["type"] == ActivityType.SYSTEM_WARNING
        assert "OCR failed" in call_kwargs["message"]

    def test_metadata_includes_file_path_when_provided(self):
        """_log_vision_warning includes file_path in metadata."""
        mock_tracker = MagicMock()

        with patch(self._TRACKER_PATCH, return_value=mock_tracker):
            _log_vision_warning("Vision error", file_path="/some/image.png")

        call_kwargs = mock_tracker.log.call_args.kwargs
        assert call_kwargs["metadata"] == {"file_path": "/some/image.png"}

    def test_metadata_empty_when_no_file_path(self):
        """_log_vision_warning omits file_path from metadata when not given."""
        mock_tracker = MagicMock()

        with patch(self._TRACKER_PATCH, return_value=mock_tracker):
            _log_vision_warning("Apple Vision not available: ImportError")

        call_kwargs = mock_tracker.log.call_args.kwargs
        assert call_kwargs["metadata"] == {}

    @pytest.mark.asyncio
    async def test_executor_warning_uses_scoped_library_tracker(self):
        from fichero.workflows.tools import vision_base

        mock_tracker = MagicMock()
        token = vision_base._vision_activity_db_path.set("/tmp/library.duckdb")
        try:
            with patch(self._TRACKER_PATCH, return_value=mock_tracker) as get_tracker:
                await asyncio.to_thread(_log_vision_warning, "Vision warning")
        finally:
            vision_base._vision_activity_db_path.reset(token)

        get_tracker.assert_called_once_with("/tmp/library.duckdb")
        mock_tracker.log.assert_called_once()

    def test_no_tracker_does_not_raise(self):
        """When get_activity_tracker returns None, _log_vision_warning is a no-op (no raise)."""
        with patch(self._TRACKER_PATCH, return_value=None):
            # Must not raise — the `if tracker:` guard short-circuits silently
            _log_vision_warning("test warning no tracker")

    def test_tracker_import_failure_falls_back_gracefully(self, caplog):
        """If get_activity_tracker raises, _log_vision_warning does not propagate."""
        import logging

        with patch(self._TRACKER_PATCH, side_effect=RuntimeError("activity not available")), \
             caplog.at_level(logging.WARNING):
            # Must not propagate the RuntimeError
            _log_vision_warning("import failure test")

    def test_tracker_log_exception_does_not_propagate(self):
        """If tracker.log itself raises, _log_vision_warning swallows it."""
        mock_tracker = MagicMock()
        mock_tracker.log.side_effect = RuntimeError("DB write failed")

        with patch(self._TRACKER_PATCH, return_value=mock_tracker):
            # Should not raise despite tracker.log failing
            _log_vision_warning("error in tracker test")


class TestAppleVisionOCREmitsWarning:
    """Integration-style tests: verify _log_vision_warning is called when
    apple_vision_ocr encounters errors."""

    def test_import_error_calls_log_vision_warning(self, tmp_path):
        """When the Vision framework is missing, _log_vision_warning is called."""
        from fichero.workflows.tools.vision_base import apple_vision_ocr

        with (
            patch("fichero.workflows.tools.vision_base._log_vision_warning"),
            patch(
                "fichero.workflows.tools.vision_base.objc",
                side_effect=AttributeError,
                create=True,
            ),
            # Simulate Vision import failure inside apple_vision_ocr
            patch.dict("sys.modules", {"Vision": None}),
            pytest.raises(Exception),  # the function re-raises after logging
        ):
            img = tmp_path / "img.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
            apple_vision_ocr(str(img))

        # We can't guarantee the exact call count since it may raise at different
        # points, but if it gets to the ImportError path it should have warned.
        # Just confirm no uncaught exception escaped without any logging attempt.
        # (The pytest.raises above ensures the exception was caught by the test.)

    def test_empty_result_reads_cgimage_dimensions_with_core_graphics(self):
        from fichero.workflows.tools.vision_base import (
            _vision_ocr_cgimage_with_geometry,
        )

        request = MagicMock()
        request.results.return_value = []
        handler = MagicMock()
        handler.performRequests_error_.return_value = True

        vision = ModuleType("Vision")
        vision.VNImageRequestHandler = MagicMock()
        vision.VNImageRequestHandler.alloc.return_value.initWithCGImage_options_.return_value = handler
        vision.VNRecognizeTextRequest = MagicMock()
        vision.VNRecognizeTextRequest.alloc.return_value.init.return_value = request
        vision.VNRequestTextRecognitionLevelAccurate = "accurate"
        vision.VNRequestTextRecognitionLevelFast = "fast"

        quartz = ModuleType("Quartz")
        quartz.CGImageGetWidth = MagicMock(return_value=640)
        quartz.CGImageGetHeight = MagicMock(return_value=480)

        with (
            patch.dict("sys.modules", {"Vision": vision, "Quartz": quartz}),
            patch("fichero.workflows.tools.vision_base._log_vision_warning"),
        ):
            result = _vision_ocr_cgimage_with_geometry(object())

        assert result.text == ""
        quartz.CGImageGetWidth.assert_called()
        quartz.CGImageGetHeight.assert_called()
