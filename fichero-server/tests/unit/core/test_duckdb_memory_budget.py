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
    ds._applied.clear()
    yield
    ds._instances.clear()
    ds._instances.update(saved)
    ds._applied.clear()


def _limit(conn) -> int:
    return ds.parse_size(conn.execute("SELECT current_setting('memory_limit')").fetchone()[0].replace(" ", ""))


def _near(got: int, want: float) -> bool:
    """DuckDB prints a size to one decimal in its largest unit ("1.5 GiB" for 1638 MiB), so a limit of a GiB or more is
    read back to within 0.11 GiB, and a MiB figure to within a MiB."""
    return abs(got - want) <= (0.11 * GIB if max(got, want) >= GIB else 1024**2)


def _open(tmp_path, name):
    return ds.connect_utc(str(tmp_path / f"{name}.duckdb"))


def test_four_open_databases_on_16_gib_stay_within_the_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    conns = [_open(tmp_path, f"db{i}") for i in range(4)]
    budget = 16 * GIB * ds.BUDGET_FRACTION
    limits = [_limit(c) for c in conns]
    # DuckDB reports its own rounding (a MiB figure), so compare with a MiB of slack per instance.
    assert sum(limits) <= budget + 4 * 1024**2
    assert all(_near(x, budget / 4) for x in limits)  # the first three were re-applied when the fourth opened
    for c in conns:
        c.close()


def test_the_share_grows_back_when_an_instance_closes(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    a, b = _open(tmp_path, "a"), _open(tmp_path, "b")
    assert _limit(a) < 0.9 * 16 * GIB * ds.BUDGET_FRACTION  # half each
    b.close()
    ds.rebalance_memory_limits()
    assert _near(_limit(a), 16 * GIB * ds.BUDGET_FRACTION)
    a.close()


def test_the_floor_wins_over_many_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)  # 0.8 GiB total, ten instances
    conns = [_open(tmp_path, f"db{i}") for i in range(10)]
    assert all(_near(_limit(c), ds.FLOOR_BYTES) for c in conns)
    for c in conns:
        c.close()


def test_the_env_value_is_the_total(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    monkeypatch.setenv(ds.DUCKDB_MEMORY_LIMIT_ENV, "2GiB")
    a, b = _open(tmp_path, "a"), _open(tmp_path, "b")
    assert _near(_limit(a), GIB) and _near(_limit(b), GIB)
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


def test_a_second_connect_to_an_open_file_sets_nothing_on_the_others(tmp_path, monkeypatch):
    """WHY (review 273 LOW): every poll connects; each connect re-probed and re-SET every open instance under a lock."""
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    sets = []
    real = ds._set_limit
    monkeypatch.setattr(ds, "_set_limit", lambda conn, limit: (sets.append(limit), real(conn, limit))[1])
    a, b = _open(tmp_path, "a"), _open(tmp_path, "b")
    sets.clear()
    again = _open(tmp_path, "a")  # a poll
    again2 = _open(tmp_path, "b")
    assert sets == []
    for c in (a, b, again, again2):
        c.close()


def test_a_new_instance_sets_only_the_ones_whose_share_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)  # 0.8 GiB: three at the floor already
    sets = []
    real = ds._set_limit
    monkeypatch.setattr(ds, "_set_limit", lambda conn, limit: (sets.append(limit), real(conn, limit))[1])
    conns = [_open(tmp_path, f"db{i}") for i in range(4)]
    sets.clear()
    conns.append(_open(tmp_path, "db4"))  # share stays at the floor for everyone: only the newcomer is set
    assert sets == [ds.FLOOR_BYTES]
    for c in conns:
        c.close()


def test_a_file_closed_and_opened_again_gets_its_share_back(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    a = _open(tmp_path, "a")
    a.close()
    again = _open(tmp_path, "a")  # a new instance, back at DuckDB's default
    assert _near(_limit(again), 16 * GIB * ds.BUDGET_FRACTION)
    again.close()


class _RefusesANewSpillDirectory:
    """A connection to an instance that has already spilled: DuckDB refuses to switch its temp directory then."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        if sql.startswith("SET temp_directory"):
            import duckdb

            raise duckdb.InvalidInputException("Cannot switch temporary directory after the current one has been used")
        return self._conn.execute(sql, params) if params is not None else self._conn.execute(sql)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_a_refused_spill_directory_does_not_stop_the_cap_from_applying(tmp_path, monkeypatch, caplog):
    """Ann's log (2026-10-26): "Could not cap DuckDB memory: Cannot switch temporary directory after the current one has
    been used" every few seconds. The SET of the spill directory raised first, so the memory cap after it never ran."""
    import duckdb

    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 16 * GIB)
    real = duckdb.connect(str(tmp_path / "a.duckdb"))
    default = _limit(real)
    with caplog.at_level("WARNING"):
        ds.apply_memory_limit(_RefusesANewSpillDirectory(real), key="a")
    assert _limit(real) < default, "the cap never applied"
    assert "Could not cap DuckDB memory" not in caplog.text
    real.close()
