"""A DuckDB memory budget scaled to the Mac (manager ruling 2026-10-19): ~10% of physical memory, split across the open
instances, never under a 256 MiB floor; the env override is the total; the spill dir is set and is not a bare /tmp."""
from __future__ import annotations

import pytest

from fichero_server.core import duckdb_session as ds

GIB = 1024**3


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv(ds.DUCKDB_MEMORY_LIMIT_ENV, raising=False)
    saved = dict(ds._instances)
    ds._instances.clear()
    yield
    ds._instances.clear()
    ds._instances.update(saved)


def _limit(conn) -> int:
    return ds.parse_size(conn.execute("SELECT current_setting('memory_limit')").fetchone()[0].replace(" ", ""))


def _open(tmp_path, name):
    return ds.connect_utc(str(tmp_path / f"{name}.duckdb"))


def test_four_open_databases_on_16_gib_stay_within_the_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    conns = [_open(tmp_path, f"db{i}") for i in range(4)]
    budget = 16 * GIB * ds.BUDGET_FRACTION
    limits = [_limit(c) for c in conns]
    # DuckDB reports its own rounding (a MiB figure), so compare with a MiB of slack per instance.
    assert sum(limits) <= budget + 4 * 1024**2
    assert all(abs(x - budget / 4) <= 1024**2 for x in limits)  # the first three were re-applied when the fourth opened
    for c in conns:
        c.close()


def test_the_share_grows_back_when_an_instance_closes(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    a, b = _open(tmp_path, "a"), _open(tmp_path, "b")
    assert _limit(a) < 0.9 * 16 * GIB * ds.BUDGET_FRACTION  # half each
    b.close()
    ds.rebalance_memory_limits()
    assert abs(_limit(a) - 16 * GIB * ds.BUDGET_FRACTION) <= 1024**2
    a.close()


def test_the_floor_wins_over_many_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)  # 0.8 GiB total, ten instances
    conns = [_open(tmp_path, f"db{i}") for i in range(10)]
    assert all(abs(_limit(c) - ds.FLOOR_BYTES) <= 1024**2 for c in conns)
    for c in conns:
        c.close()


def test_the_env_value_is_the_total(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    monkeypatch.setenv(ds.DUCKDB_MEMORY_LIMIT_ENV, "2GiB")
    a, b = _open(tmp_path, "a"), _open(tmp_path, "b")
    assert abs(_limit(a) - GIB) <= 1024**2 and abs(_limit(b) - GIB) <= 1024**2
    a.close()
    b.close()


def test_an_unusable_env_value_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv(ds.DUCKDB_MEMORY_LIMIT_ENV, "lots")
    with pytest.raises(RuntimeError, match="refusing to run this connection unbounded"):
        _open(tmp_path, "a")


def test_temp_directory_is_set_and_not_a_bare_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    conn = _open(tmp_path, "a")
    spill = conn.execute("SELECT current_setting('temp_directory')").fetchone()[0]
    assert spill.endswith("fichero-duckdb-spill")
    assert not spill.startswith(("/tmp/", "/private/tmp/"))
    conn.close()


def test_parse_size():
    assert ds.parse_size("1.5GB") == 1_500_000_000
    assert ds.parse_size("256 MiB") == 256 * 1024**2
    with pytest.raises(ValueError):
        ds.parse_size("lots")
