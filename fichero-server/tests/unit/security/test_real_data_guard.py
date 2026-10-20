"""runtime.dev-engine-refuses-real-data: a dev engine's base path is never the owner's real libraries."""
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_server.security import real_data_guard as guard

REPO = Path(__file__).resolve().parents[4]
LAUNCHERS = ("fichero-server/scripts/start_backend.py", "fichero-server/scripts/start_fichero_server.sh",
             "scripts/start_dev_local_engine.sh", "scripts/realrun_seeded.sh", "scripts/acceptance/_engine.py",
             "fichero-server/scripts/_engine_harness.py")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "Fichero" / "Library One.fichero").mkdir(parents=True)
    (tmp_path / "Fichero Projects").mkdir()
    (tmp_path / "Fichero Dev Test" / "state").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("inside", ["Fichero", "Fichero/Library One.fichero", "Fichero/new/deeper",
                                    "Fichero Projects", "Fichero Projects/x", "fichero", "FICHERO PROJECTS/y"])
def test_a_base_inside_the_real_data_is_refused_in_words(home: Path, inside: str) -> None:
    said = guard.refusal(home / inside, home)
    assert said and "real libraries" in said and "Refusing to start" in said
    with pytest.raises(SystemExit) as stop:
        guard.refuse_real_base(home / inside, home)
    assert stop.value.code != 0


def test_a_symlink_into_the_real_data_is_refused(home: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    link = tmp_path_factory.mktemp("elsewhere") / "state"
    link.symlink_to(home / "Fichero")
    assert guard.refusal(link, home)
    assert guard.refusal(link / "child", home)


@pytest.mark.parametrize("fine", ["Fichero Dev Test/state", "Fichero Dev Test", "Fichero2", "scratch"])
def test_a_scratch_base_or_a_sibling_of_the_real_folders_is_allowed(home: Path, fine: str) -> None:
    assert guard.refusal(home / fine, home) is None


def test_no_base_path_is_not_a_refusal(home: Path) -> None:
    assert guard.refusal(None, home) is None and guard.refusal("  ", home) is None


def test_the_command_line_form_exits_non_zero_for_the_real_data_and_zero_for_scratch(home: Path) -> None:
    env = {"PYTHONPATH": str(REPO / "fichero-server/src"), "HOME": str(home), "PATH": "/usr/bin:/bin"}

    def run(path: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "fichero_server.security.real_data_guard", str(path)],
                              env=env, capture_output=True, text=True)

    refused = run(home / "Fichero")
    assert refused.returncode != 0 and "real libraries" in refused.stderr
    assert run(home / "Fichero Dev Test" / "state").returncode == 0


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_every_dev_engine_launcher_calls_the_guard(launcher: str) -> None:
    assert "real_data_guard" in (REPO / launcher).read_text(encoding="utf-8"), launcher
