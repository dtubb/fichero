"""Sidecar suffixes are skipped by folder ingest, never imported as documents.

The Marshall staging convention (2026-08-16, _import/README.md) puts three
derived sidecars beside every page; before these suffixes were recognized a
plain folder ingest created ~450 junk text/JSON documents per diary.
"""
from pathlib import Path

from fichero_server.importers.ingest import _is_sidecar_file


def test_staging_sidecar_suffixes_are_recognized(tmp_path: Path) -> None:
    for name in (
        "NCM_Diary_1923IMG_010_part_1.jpg.iffy.json",
        "NCM_Diary_1923IMG_010_part_1.jpg.transcript.txt",
        "NCM_Diary_1923IMG_010_part_1.jpg.entities.json",
        "NCM_Diary_1923IMG_010_part_1.jpg.renditions.json",
        "photo.xmp",
    ):
        assert _is_sidecar_file(tmp_path / name), name


def test_primary_documents_are_not_sidecars(tmp_path: Path) -> None:
    for name in (
        "NCM_Diary_1923IMG_010_part_1.jpg",
        # A plain transcript folder's .txt is a real document — only the
        # double-suffix ".jpg.transcript.txt" form is a sidecar.
        "transcript.txt",
        "notes.json",
    ):
        assert not _is_sidecar_file(tmp_path / name), name
