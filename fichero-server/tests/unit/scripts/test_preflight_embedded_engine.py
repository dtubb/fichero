"""The embedded-engine preflight checks the directory Briefcase actually creates.

Regression guard for the wrong-path staleness diff (fixed in 985cf9c7e): the
script compared staged content at ``Contents/Resources/app/fichero`` — a
directory Briefcase never creates — so ``engine_is_current`` reported STALE
forever. The staged directory name is the Briefcase APP KEY
(``[tool.briefcase.app.<key>]`` in fichero-server/pyproject.toml), so these
tests tie the script to that source of truth: reverting to the old path OR
renaming the app key without updating the script fails here.

Also pins the fm-bridge honesty fix: a MISSING gitignored binary must say it
is missing (and that rebuilding will not create it), never the untrue
"STALE (engine sources are newer)".
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "preflight-embedded-engine.sh"
PYPROJECT = REPO_ROOT / "fichero-server" / "pyproject.toml"


def _script_text() -> str:
    text = SCRIPT.read_text()
    assert text, f"{SCRIPT} is empty — this guard measures nothing"
    return text


def _briefcase_app_key() -> str:
    """The one Briefcase app key — the staged directory's real name."""
    keys = re.findall(r"\[tool\.briefcase\.app\.([A-Za-z0-9_]+)\]", PYPROJECT.read_text())
    assert keys, "no [tool.briefcase.app.<key>] section in fichero-server/pyproject.toml"
    distinct = set(keys)
    assert len(distinct) == 1, f"expected one Briefcase app key, found {sorted(distinct)}"
    return distinct.pop()


def test_staged_paths_use_the_briefcase_app_key():
    """Every Contents/Resources/app/<dir> reference names the app key.

    This is the fixture that FAILS against the old ``app/fichero`` path: with
    the app key ``fichero_server``, any reverted reference shows up in
    ``mismatched`` below.
    """
    key = _briefcase_app_key()
    staged_dirs = re.findall(r"Contents/Resources/app/([A-Za-z0-9_]+)", _script_text())
    assert staged_dirs, "the script no longer references the staged app directory at all"
    mismatched = [d for d in staged_dirs if d != key]
    assert not mismatched, (
        f"preflight compares against Contents/Resources/app/{mismatched} but Briefcase "
        f"stages the app key '{key}' — the staleness check would be blind (985cf9c7e)"
    )


def test_build_path_uses_the_briefcase_app_key():
    """The ENGINE_APP build path itself is derived from the app key too."""
    key = _briefcase_app_key()
    assert f"build/{key}/macos/app" in _script_text()


def test_missing_fm_bridge_reports_missing_not_stale():
    """An absent gitignored binary is MISSING, never 'sources are newer'."""
    text = _script_text()
    assert "fm-bridge is MISSING from engine sources" in text
    assert "rebuilding will not create it" in text
    assert "staged copy lacks fm-bridge" in text

    # The missing-bridge branches must run BEFORE the generic stale diff, or
    # the diff (which excludes fm-bridge but fails on the broken tree state)
    # answers first with the untrue message.
    missing_at = text.index("fm-bridge is MISSING from engine sources")
    stale_at = text.index("STALE (engine sources are newer")
    assert missing_at < stale_at, "the missing-bridge check must precede the stale diff"


def test_stale_message_survives_for_the_genuinely_stale_case():
    """The honest fix must not delete the real staleness report."""
    assert "STALE (engine sources are newer than the staged copy)" in _script_text()
