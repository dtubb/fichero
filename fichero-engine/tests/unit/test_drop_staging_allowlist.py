"""Finder drop staging is readable, and NOTHING ELSE became readable (#4223).

Every Finder drop returned 403 when the engine runs as a separate process (the
default Dev Local scheme). The app stages drops into
`<container>/Data/tmp/fichero-drop-<uuid>/`, which no allow-list entry covered,
and the bookmark fallback cannot help: the app mints a TRANSIENT, unpersisted
grant, and grants live in the engine process's own `_GRANTED`, which an
externally started engine has no channel to reach.

This is a SECURITY BOUNDARY, so the tests that matter are the ones asserting
what is still DENIED. `~/Library/Containers` holds every sandboxed app's
private data — Mail, Messages — and the widening that fixes drag-and-drop is
one directory away from exposing all of it.

A guard never observed to fire is not protection, so the denial cases are
written so that a wider rule fails them.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fichero.api.main import (
    _is_allowed_local_path,
    _is_sandbox_container_drop_staging,
)

HOME = Path("/Users/tester")
CONTAINER = HOME / "Library" / "Containers" / "app.fichero.fichero"
MAIL = HOME / "Library" / "Containers" / "com.apple.mail"
DROP = CONTAINER / "Data" / "tmp" / "fichero-drop-2B7F"
SANDBOX_HOME = CONTAINER / "Data"


def _allowed(path: Path, home: Path = HOME) -> bool:
    return _is_sandbox_container_drop_staging(path, home)


class TestTheDropActuallyWorks:
    """The bug: these were all 403."""

    def test_a_staged_file_is_readable(self):
        assert _allowed(DROP / "scan.jpg")

    def test_the_staging_directory_itself_is_readable(self):
        """A folder drop hands the engine the directory, not a file."""
        assert _allowed(DROP)

    def test_nested_content_is_readable(self):
        assert _allowed(DROP / "subfolder" / "page-01.tif")


class TestWhatMustStayDENIED:
    """Each of these passes only because the rule is narrow. Widen it and they fail."""

    @pytest.mark.parametrize(
        ("label", "path"),
        [
            ("another app's tmp", MAIL / "Data" / "tmp" / "secret.sqlite"),
            ("another app's container", MAIL / "Data" / "Library" / "Mail" / "x.emlx"),
            ("our container root", CONTAINER / "secret.txt"),
            ("our Data root", CONTAINER / "Data" / "secret.txt"),
            ("our Data/tmp, no drop prefix", CONTAINER / "Data" / "tmp" / "scratch" / "x"),
            ("the Containers root itself", HOME / "Library" / "Containers" / "x"),
            ("a lookalike prefix", CONTAINER / "Data" / "tmp" / "fichero-dropper" / "x"),
            ("home itself", HOME / "x"),
        ],
    )
    def test_denied(self, label, path):
        assert not _allowed(path), f"{label} must not be readable: {path}"

    def test_the_prefix_is_what_denies_other_apps(self):
        """The single-component container rule ALONE is not enough.

        The sibling Application Support helper accepts any container. Without
        the `fichero-drop-` prefix this would do the same for `Data/tmp`, and
        every sandboxed app's scratch space would become readable.
        """
        mail_tmp = MAIL / "Data" / "tmp" / "anything"

        assert not _allowed(mail_tmp)


class TestTheSandboxedEngineShapeToo:
    """App Store / embedded: the sandbox redirects HOME into the container.

    Established by simulation rather than assumed — without this the shipping
    build would still 403 on every drop.
    """

    def test_the_same_directory_is_readable_under_a_redirected_home(self):
        assert _allowed(DROP / "scan.jpg", home=SANDBOX_HOME)

    def test_a_redirected_home_does_not_expose_the_whole_container(self):
        assert not _allowed(SANDBOX_HOME / "Library" / "secret", home=SANDBOX_HOME)
        assert not _allowed(SANDBOX_HOME / "tmp" / "scratch" / "x", home=SANDBOX_HOME)


class TestTheWidthOfTheRuleIsPinned:
    """The requirement: fail if the allow-list widens beyond one container.

    Mutation-checked — accepting two path components for the container makes
    `test_two_component_container_is_rejected` fail.
    """

    def test_two_component_container_is_rejected(self):
        """`<a>/<b>/Data/tmp/fichero-drop-x` must NOT match.

        A rule that walked further down the tree, or matched `Data/tmp`
        anywhere beneath Containers, would accept this.
        """
        deep = HOME / "Library" / "Containers" / "outer" / "inner"
        path = deep / "Data" / "tmp" / "fichero-drop-x" / "file.jpg"

        assert not _allowed(path)

    def test_drop_dir_must_be_exactly_at_data_tmp(self):
        """Not `Data/tmp/<anything>/fichero-drop-x`."""
        path = CONTAINER / "Data" / "tmp" / "nested" / "fichero-drop-x" / "f.jpg"

        assert not _allowed(path)


class TestWiredIntoTheRealCheck:
    """The helper must be reachable from `_is_allowed_local_path`.

    A helper nobody calls reads as protection and provides none — the same
    defect found by mutation in the ingest durability work.
    """

    def test_the_allow_list_consults_the_drop_helper(self):
        with patch.object(Path, "home", staticmethod(lambda: HOME)):
            with patch("fichero.api.main._is_sandbox_container_drop_staging") as helper:
                helper.return_value = False
                _is_allowed_local_path(str(DROP / "scan.jpg"))

        assert helper.called, "_is_allowed_local_path never consulted the drop helper"
