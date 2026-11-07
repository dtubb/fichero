"""Tests for jobs.progress calls in sync_folder and kept_export (#6205 rework).
Ensuring that per-item progress pings are actually sent so the watchdog doesn't
false-positive on long-running healthy jobs. Removing the progress calls turns
these red."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from fichero_server.execution import jobs
from fichero_server import sync_folder, kept_export
import fichero_server.page_export as page_export


@pytest.fixture
def spy_progress(monkeypatch):
    spy = MagicMock(name="jobs.progress")
    monkeypatch.setattr(jobs, "progress", spy)
    return spy


@pytest.fixture
def job_id(monkeypatch):
    monkeypatch.setattr(jobs, "current_job_id", lambda: "test-job-123")


def test_sync_folder_write_pings_progress(db, spy_progress, job_id, monkeypatch):
    """sync_folder.write calls jobs.progress for each format (#6205)."""
    folder = {"id": "f1", "path": "/tmp/f1", "formats": ["alto", "pagexml"],
              "adopted": False, "intake": False, "mode": "index"}
    monkeypatch.setattr(sync_folder, "_folder", lambda db, fid: folder)
    monkeypatch.setattr(sync_folder, "_record", lambda *a, **k: None)
    
    # Mock export_page to raise so the loop continues past the progress call
    mock_export = MagicMock(side_effect=page_export.ExportRefused("test"))
    monkeypatch.setattr(page_export, "export_page", mock_export)
    
    sync_folder.write(db, "f1:doc1")
    
    assert spy_progress.call_count == 2
    assert spy_progress.call_args_list[0].args[0] == "test-job-123"
    assert spy_progress.call_args_list[1].args[0] == "test-job-123"


def test_sync_folder_write_back_pings_progress(db, spy_progress, job_id, monkeypatch):
    """sync_folder._write_back calls jobs.progress for each row (#6205)."""
    folder = {"id": "f1", "path": "/tmp/f1", "adopted": True, "intake": False, "mode": "index"}
    rows = [("file1.alto", "alto", "sha1", None), ("file2.alto", "alto", "sha2", None)]
    
    mock_fetchall = MagicMock(return_value=rows)
    monkeypatch.setattr(db, "execute_fetchall", mock_fetchall)
    monkeypatch.setattr(sync_folder, "_record", lambda *a, **k: None)
    monkeypatch.setattr(sync_folder, "_changed_outside", lambda *a, **k: None)
    
    mock_export = MagicMock(side_effect=page_export.ExportRefused("test"))
    monkeypatch.setattr(page_export, "export_page", mock_export)
    
    sync_folder._write_back(db, folder, Path("/tmp/f1"), "doc1")
    
    assert spy_progress.call_count == 2
    assert spy_progress.call_args_list[0].args[0] == "test-job-123"


def test_sync_folder_read_pings_progress(db, spy_progress, job_id, monkeypatch):
    """sync_folder.read calls jobs.progress for each row (#6205)."""
    folder = {"id": "f1", "path": "/tmp/f1", "adopted": False, "intake": True, "mode": "index"}
    monkeypatch.setattr(sync_folder, "_folder", lambda db, fid: folder)
    monkeypatch.setattr(sync_folder, "_arrivals", lambda db, f: [])
    monkeypatch.setattr(sync_folder, "_follow_renames", lambda db, f, a: [])
    monkeypatch.setattr(sync_folder, "_record", lambda *a, **k: None)
    
    rows = [("file1.alto", "doc1", "alto", "sha1", None, "written")]
    mock_fetchall = MagicMock(return_value=rows)
    monkeypatch.setattr(db, "execute_fetchall", mock_fetchall)
    
    sync_folder.read(db, "f1")
    
    assert spy_progress.call_count == 1
    assert spy_progress.call_args_list[0].args[0] == "test-job-123"


def test_kept_export_write_pings_progress(db, spy_progress, job_id, monkeypatch, tmp_path):
    """kept_export.write calls jobs.progress for each unit (#6205)."""
    export = {"id": "e1", "folder": str(tmp_path), "format": "alto", "per": "page"}
    monkeypatch.setattr(kept_export, "_export", lambda db, eid: export)
    monkeypatch.setattr(kept_export, "_units", lambda db, e: [MagicMock(), MagicMock()])
    monkeypatch.setattr(kept_export, "_render", lambda *a, **k: None)
    monkeypatch.setattr(kept_export, "_put", lambda *a, **k: None)
    
    kept_export.write(db, "e1")
    
    assert spy_progress.call_count == 2
    assert spy_progress.call_args_list[0].args[0] == "test-job-123"