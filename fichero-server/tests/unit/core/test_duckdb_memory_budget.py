"""A DuckDB memory budget scaled to the Mac (manager ruling 2026-10-19): ~10% of physical memory, never under 1 GiB
(the 2026-10-30 Air OOM), split across the open library instances with the engine's own small files taking a fixed
slice, never under a 256 MiB floor; the env override is the total; the spill dir is set and is not a bare /tmp."""
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
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)  # 1 GiB total, ten instances
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
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)  # 1 GiB: four at the floor already
    sets = []
    real = ds._set_limit
    monkeypatch.setattr(ds, "_set_limit", lambda conn, limit: (sets.append(limit), real(conn, limit))[1])
    conns = [_open(tmp_path, f"db{i}") for i in range(5)]
    sets.clear()
    conns.append(_open(tmp_path, "db5"))  # share stays at the floor for everyone: only the newcomer is set
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


# --- the 2026-10-30 Air OOM: 8 GB, two libraries open plus the engine's own two files ------------------------------


def test_an_8_gb_mac_gives_a_library_at_least_a_gib_minus_the_small_files(tmp_path, monkeypatch):
    """The Air: app.duckdb + global.fichero + GHG + GHG 12 open, 10% of 8 GB = 819 MiB, four ways = the 256 MiB floor,
    and a 69k-document library failed 170 reads in a morning. The budget is never under 1 GiB; the engine's two small
    files take 64 MiB each; the two libraries share the rest."""
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)
    (tmp_path / "global.fichero").mkdir()
    app = _open(tmp_path, "app")
    glob = ds.connect_utc(str(tmp_path / "global.fichero" / "fichero.duckdb"))
    (tmp_path / "GHG.fichero").mkdir()
    (tmp_path / "GHG 12.fichero").mkdir()
    ghg = ds.connect_utc(str(tmp_path / "GHG.fichero" / "fichero.duckdb"))
    ghg12 = ds.connect_utc(str(tmp_path / "GHG 12.fichero" / "fichero.duckdb"))
    assert _near(_limit(app), ds.SMALL_INSTANCE_BYTES)
    assert _near(_limit(glob), ds.SMALL_INSTANCE_BYTES)
    each = (GIB - 2 * ds.SMALL_INSTANCE_BYTES) / 2
    assert each >= 448 * 1024**2
    assert _near(_limit(ghg), each) and _near(_limit(ghg12), each)
    for c in (app, glob, ghg, ghg12):
        c.close()


def test_a_single_library_on_8_gb_gets_the_whole_gib_less_the_small_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)
    app = _open(tmp_path, "app")
    (tmp_path / "GHG.fichero").mkdir()
    ghg = ds.connect_utc(str(tmp_path / "GHG.fichero" / "fichero.duckdb"))
    assert _near(_limit(ghg), GIB - ds.SMALL_INSTANCE_BYTES)
    app.close()
    ghg.close()


def test_a_small_mac_runs_few_duckdb_threads(tmp_path, monkeypatch):
    """Each DuckDB thread owns a 16 MiB string arena while it scans; eight of them on the Air's share was the OOM."""
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 8 * GIB)
    conn = _open(tmp_path, "a")
    assert int(conn.execute("SELECT current_setting('threads')").fetchone()[0]) == ds.THREADS_ON_A_SMALL_MAC
    conn.close()
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: 32 * GIB)
    ds._instances.clear(); ds._applied.clear()
    conn = _open(tmp_path, "b")
    assert int(conn.execute("SELECT current_setting('threads')").fetchone()[0]) > ds.THREADS_ON_A_SMALL_MAC
    conn.close()


def test_a_grown_global_library_shares_as_a_library(tmp_path):
    big = tmp_path / "global.fichero" / "fichero.duckdb"
    big.parent.mkdir()
    big.write_bytes(b"\0" * (ds.SMALL_FILE_BYTES + 1))
    assert not ds.is_small_instance(str(big))
    assert ds.is_small_instance(str(tmp_path / "app.duckdb"))
