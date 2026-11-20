"""`source.onboard.stages.sample-run-reuses` (#6733 item 10): a try's scratch copy is deleted and made again at the
same path; the second copy has its own sync tables ("Table with name sync_folders does not exist" on every second
Read try)."""
from __future__ import annotations

import shutil

from fichero_server import sync_folder
from fichero_server.db.manager import db_manager


def test_a_copy_made_again_at_the_same_path_has_its_sync_tables(tmp_path):
    path = tmp_path / "copy.fichero"
    for sub in ("lance", "storage", "files"):
        (path / sub).mkdir(parents=True)
    first = db_manager.get_database(path)
    assert sync_folder._folders(first) == []
    db_manager.close_database(path)
    shutil.rmtree(path)
    for sub in ("lance", "storage", "files"):
        (path / sub).mkdir(parents=True)
    second = db_manager.get_database(path)
    try:
        assert sync_folder._folders(second) == []
    finally:
        db_manager.close_database(path)
