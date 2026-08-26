"""One connection per PACKAGE, however the path is spelled (#2518).

Proven live 2026-08-25: the create flow held TWO DuckDB connections to one
temp package — one under `/var/folders/…`, one under `/private/var/…`.
`DatabaseManager._cache_key` (NFC + realpath) is the one key form; get,
close, and quiesce all funnel through it.
"""

from fichero_server.db.manager import DatabaseManager


def test_symlink_spellings_share_one_cache_key(tmp_path):
    real = tmp_path / "real" / "Lib.fichero"
    real.mkdir(parents=True)
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(tmp_path / "real")
    alias = alias_parent / "Lib.fichero"

    assert DatabaseManager._cache_key(real) == DatabaseManager._cache_key(alias)


def test_trailing_slash_and_plain_share_one_cache_key(tmp_path):
    pkg = tmp_path / "Lib.fichero"
    pkg.mkdir()
    assert DatabaseManager._cache_key(str(pkg)) == DatabaseManager._cache_key(str(pkg) + "/")
