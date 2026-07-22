"""Regression tests for camera-folder ingest provenance."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fichero.models import Document


class TestCameraIngestProvenance:
    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_ingest_file_records_source_folder_and_mtime(self, _mock_bookmark, tmp_path):
        from fichero.importers.ingest import ingest_file

        camera_dir = tmp_path / "camera-import"
        camera_dir.mkdir()
        file = camera_dir / "IMG_0001.JPG"
        file.write_bytes(b"camera frame data")

        doc = ingest_file(
            file,
            extract_metadata=False,
            extract_text=False,
            save=False,
        )

        assert doc.metadata["source_path"] == str(file)
        assert doc.metadata["source_folder"] == str(camera_dir)
        assert "source_mtime" in doc.metadata

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_ingest_folder_skips_unchanged_duplicate_camera_file(
        self, _mock_bookmark, tmp_path
    ):
        from fichero.importers.ingest import _file_checksum, ingest_folder

        camera_dir = tmp_path / "camera-import"
        camera_dir.mkdir()
        file = camera_dir / "IMG_0001.JPG"
        file.write_bytes(b"camera frame data")
        checksum = _file_checksum(file)

        mock_db = MagicMock()
        mock_db.all.return_value = [
            Document(
                name=file.name,
                path=str(file),
                metadata={"source_path": str(file), "checksum": checksum},
            )
        ]
        mock_db.save.side_effect = lambda *_args, **_kwargs: None

        docs = ingest_folder(camera_dir, db=mock_db, create_collection=False)

        assert docs == []
        mock_db.save.assert_not_called()
