"""`scripts/fresh-launch.sh` sets the app's data aside and puts it back, deleting nothing (2026-10-10).

Run in a throwaway HOME with FICHERO_FRESH_TEST=1 (the real app is never quit) and
FICHERO_FRESH_NO_LAUNCH=1 (nothing is opened)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "fresh-launch.sh"


def _run(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home), "FICHERO_FRESH_TEST": "1", "FICHERO_FRESH_NO_LAUNCH": "1"}
    return subprocess.run(["zsh", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_set_aside_then_restore_keeps_everything(tmp_path: Path) -> None:
    containers = tmp_path / "Library" / "Containers"
    real = containers / "app.fichero.fichero"
    (real / "Data").mkdir(parents=True)
    (real / "Data" / "prefs.plist").write_text("real")
    (containers / "app.fichero.fichero.fichero_server").mkdir()
    app = tmp_path / "Fichero.app"
    app.mkdir()

    first = _run(tmp_path, str(app))
    assert first.returncode == 0, first.stderr
    assert not real.exists() and (containers / "app.fichero.fichero.fresh-saved" / "Data" / "prefs.plist").exists()
    assert _run(tmp_path, str(app)).returncode == 1, "a second set-aside is refused, never overwrites"

    (real / "Data").mkdir(parents=True)  # what the cold app made
    (real / "Data" / "prefs.plist").write_text("cold")
    restored = _run(tmp_path, "--restore")
    assert restored.returncode == 0, restored.stderr
    assert (real / "Data" / "prefs.plist").read_text() == "real"
    tries = [p for p in containers.iterdir() if ".fresh-try-" in p.name]
    assert any((p / "Data" / "prefs.plist").read_text() == "cold" for p in tries if p.name.startswith("app.fichero.fichero.fresh"))
    assert _run(tmp_path, "--restore").returncode == 1, "nothing left to restore"
