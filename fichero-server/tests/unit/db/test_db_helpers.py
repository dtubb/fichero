from __future__ import annotations

from fichero_server.db import _collect_folder_descendants_helper


class _RaisingConn:
    def execute(self, _query, _params):
        raise RuntimeError("db error")


def test_collect_folder_descendants_returns_root_when_query_errors():
    """Helper should fail soft and still include the root folder id."""
    descendants = _collect_folder_descendants_helper(_RaisingConn(), "folder-123")
    assert descendants == {"folder-123"}
