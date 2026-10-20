"""scripts/audit_copied_from.py (#5906, ## 579): the read-only audit refuses anything that could be a live library."""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import audit_copied_from as audit  # noqa: E402


def _library(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute('CREATE TABLE "documents" (id VARCHAR, name VARCHAR, path VARCHAR, metadata VARCHAR)')
    con.execute("""INSERT INTO "documents" VALUES ('d1', 'p1', 'files/p1.png', '{"copied_from": "/old/p1.png"}'), ('d2', 'p2', '/x/p2.png', '{}')""")
    con.close()
    return path


def test_a_clean_copy_is_audited_and_finds_the_repointed_page(tmp_path):
    lib = _library(tmp_path / "copy" / "lib.duckdb")
    why, found = audit.refusal(str(lib), home=tmp_path / "home")
    assert why == "" and found == lib.resolve()
    assert [row[0] for row in audit.audit(found)] == ["d1"]


def test_a_path_under_a_live_fichero_location_is_refused(tmp_path):
    home = tmp_path / "home"
    for live in (home / "Fichero" / "a" / "lib.duckdb", home / "Fichero Projects" / "lib.duckdb",
                 home / "Library" / "Containers" / "app.fichero.fichero" / "Data" / "lib.duckdb"):
        lib = _library(live)
        why, found = audit.refusal(str(lib), home=home)
        assert "live Fichero location" in why and found is None


def test_a_symlink_into_a_live_location_is_refused_after_it_is_resolved(tmp_path):
    home = tmp_path / "home"
    real = _library(home / "Fichero" / "lib.duckdb")
    link = tmp_path / "innocent" / "copy.duckdb"
    link.parent.mkdir()
    link.symlink_to(real)
    assert "live Fichero location" in audit.refusal(str(link), home=home)[0]


def test_a_library_with_a_wal_beside_it_is_refused(tmp_path):
    lib = _library(tmp_path / "copy" / "lib.duckdb")
    Path(f"{lib}.wal").write_bytes(b"x")
    why, found = audit.refusal(str(lib), home=tmp_path / "home")
    assert ".wal" in why and found is None


def test_a_folder_must_hold_exactly_one_library_and_is_not_searched_recursively(tmp_path):
    home = tmp_path / "home"
    two = tmp_path / "two"
    _library(two / "a.duckdb"), _library(two / "b.duckdb")
    assert "holds 2 library files" in audit.refusal(str(two), home=home)[0]
    deep = tmp_path / "deep"
    _library(deep / "inner" / "lib.duckdb")  # only below the folder: nothing directly in it
    assert "holds 0 library files" in audit.refusal(str(deep), home=home)[0]
    one = tmp_path / "one"
    lib = _library(one / "lib.duckdb")
    assert audit.refusal(str(one), home=home) == ("", lib.resolve())


def test_main_exits_non_zero_when_it_refuses_and_says_why(tmp_path, capsys):
    home_like = Path.home() / "Fichero"
    code = audit.main([str(home_like / "nope.duckdb")])
    assert code == 2 and "REFUSED" in capsys.readouterr().out
