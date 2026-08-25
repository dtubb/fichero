"""TMPDIR staging packages never enter the known-libraries registry.

The app's New Library flow materializes `Untitled-<UUID>.fichero` under the
temp tree before the save panel; registering it was the ghost-library
generator (dead `Untitled-…` rows in the sidebar and Open Recent,
2026-08-25). `_is_staging_location` is the guard.
"""

from fichero_server.api.routes.library.core import _is_staging_location


def test_darwin_per_user_temp_tree_is_staging():
    assert _is_staging_location(
        "/var/folders/mw/xy123/T/Untitled-ABC.fichero"
    )
    assert _is_staging_location(
        "/private/var/folders/mw/xy123/T/Untitled-ABC.fichero"
    )


def test_sandbox_container_tmp_is_staging():
    assert _is_staging_location(
        "/Users/x/Library/Containers/app.fichero.fichero/Data/tmp/Untitled-A.fichero"
    )


def test_plain_tmp_is_staging():
    assert _is_staging_location("/tmp/Untitled-A.fichero")


def test_real_user_locations_are_not_staging():
    assert not _is_staging_location("/Users/daniel/Fichero/My Notebooks.fichero")
    assert not _is_staging_location("/Users/daniel/Documents/Lib.fichero")
