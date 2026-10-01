"""Unit tests for library prefetch / cache warm (#1918).

Covers:
- prefetch_library_caches() returns a stats dict with expected keys
- opening a library loads no embedding model (#5283: about 1.5 GB; it loads on first use)
- prefetch is idempotent (calling twice doesn't raise)
- prefetch on a non-existent package returns gracefully
"""

from __future__ import annotations

from fichero_server.db import embeddings as db_embeddings


def test_prefetch_loads_no_embedding_model(test_package, monkeypatch):
    """#5283, ruled 2026-10-01: the model is loaded by an embed or a semantic search, not by opening
    a library -- prefetch loaded it for every library opened, so every session held 1.5 GB."""
    from fichero_server.api.main import prefetch_library_caches

    loads: list[str] = []
    monkeypatch.setattr(db_embeddings, "_get_shared_embedder", lambda name, _cache: loads.append(name))
    prefetch_library_caches(test_package)
    assert loads == []


# ---------------------------------------------------------------------------
# prefetch_library_caches
# ---------------------------------------------------------------------------


def test_prefetch_library_caches_returns_stats(test_package):
    """prefetch_library_caches returns a dict with the expected keys."""
    from fichero_server.api.main import prefetch_library_caches

    stats = prefetch_library_caches(test_package)

    assert "package_path" in stats
    assert "lance_tables_opened" in stats
    assert isinstance(stats["lance_tables_opened"], int)
    assert stats["lance_tables_opened"] >= 0


def test_prefetch_library_caches_nonexistent_package(tmp_path):
    """prefetch_library_caches on a missing path returns gracefully (no raise)."""
    from fichero_server.api.main import prefetch_library_caches

    missing = tmp_path / "nonexistent.fichero"
    stats = prefetch_library_caches(missing)

    assert stats["package_path"] == str(missing)
    assert isinstance(stats["lance_tables_opened"], int)


def test_prefetch_library_caches_is_idempotent(test_package):
    """Calling prefetch twice on the same library must not raise."""
    from fichero_server.api.main import prefetch_library_caches

    stats1 = prefetch_library_caches(test_package)
    stats2 = prefetch_library_caches(test_package)

    assert stats1["package_path"] == stats2["package_path"]


def test_prefetch_empty_lance_tables_on_fresh_db(test_package):
    """A freshly created library has no LanceDB tables yet — lance_tables_opened is 0."""
    from fichero_server.api.main import prefetch_library_caches

    stats = prefetch_library_caches(test_package)

    assert stats["lance_tables_opened"] == 0, (
        "A brand-new test library has no vector tables; "
        f"got lance_tables_opened={stats['lance_tables_opened']}"
    )
