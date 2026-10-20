"""runtime.dev-engine-refuses-real-data: a dev engine's base path is never the owner's real libraries."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_server.security import real_data_guard as guard

REPO = Path(__file__).resolve().parents[4]


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "Library" / "Application Support" / "Fichero").mkdir(parents=True)
    (tmp_path / "Library" / "Containers" / "app.fichero.fichero" / "Data").mkdir(parents=True)
    (tmp_path / "Fichero" / "Library One.fichero").mkdir(parents=True)
    (tmp_path / "Fichero Projects").mkdir()
    (tmp_path / "Fichero Dev Test" / "state").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("inside", ["Fichero", "Fichero/Library One.fichero", "Fichero/new/deeper",
                                    "Fichero Projects", "Fichero Projects/x", "fichero", "FICHERO PROJECTS/y",
                                    "Library/Application Support/Fichero", "Library/Application Support/Fichero/x",
                                    "Library/Containers/app.fichero.fichero",
                                    "Library/Containers/app.fichero.fichero/Data/tmp",
                                    "Library/Containers/APP.FICHERO.dev/Data",
                                    "Library/Application Support/app.fichero.fichero",
                                    "Library/Application Support/app.fichero.fichero/state"])
def test_a_base_inside_the_real_data_is_refused_in_words(home: Path, inside: str) -> None:
    said = guard.refusal(home / inside, home)
    assert said and "Refusing to start" in said
    with pytest.raises(SystemExit) as stop:
        guard.refuse_real_base(home / inside, home)
    assert stop.value.code != 0


def test_a_symlink_into_the_real_data_is_refused(home: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    link = tmp_path_factory.mktemp("elsewhere") / "state"
    link.symlink_to(home / "Fichero")
    assert guard.refusal(link, home)
    assert guard.refusal(link / "child", home)


@pytest.mark.parametrize("fine", ["Fichero Dev Test/state", "Fichero Dev Test", "Fichero2", "scratch",
                                  "Library/Application Support/Other", "Library/Containers/com.other.app/Data"])
def test_a_scratch_base_or_a_sibling_of_the_real_folders_is_allowed(home: Path, fine: str) -> None:
    assert guard.refusal(home / fine, home) is None


@pytest.mark.parametrize("none", [None, "", "  "])
def test_no_base_path_is_refused_because_the_engine_would_write_the_real_app_state(home: Path, none) -> None:
    said = guard.refusal(none, home)
    assert said and "no base path is set" in said and "Application Support/Fichero" in said


def test_the_owners_switch_lifts_only_the_unset_and_default_state_refusals(home: Path, monkeypatch) -> None:
    monkeypatch.setenv(guard.ALLOW_REAL_STATE_ENV, "1")
    assert os.environ[guard.ALLOW_REAL_STATE_ENV] == "1"
    guard.refuse_real_base(None, home)  # unset: the real app state, on purpose
    guard.refuse_real_base(home / "Library/Application Support/Fichero", home)  # the default state dir, on purpose
    for still in ("Fichero", "Fichero Projects/x", "Library/Containers/app.fichero.fichero/Data",
                  "Library/Application Support/app.fichero.fichero"):  # never, switch or not
        with pytest.raises(SystemExit):
            guard.refuse_real_base(home / still, home)
    monkeypatch.setenv(guard.ALLOW_REAL_STATE_ENV, "yes")  # only the exact value "1"
    with pytest.raises(SystemExit):
        guard.refuse_real_base(None, home)


def test_the_command_line_form_exits_non_zero_for_the_real_data_and_zero_for_scratch(home: Path) -> None:
    env = {"PYTHONPATH": str(REPO / "fichero-server/src"), "HOME": str(home), "PATH": "/usr/bin:/bin"}

    def run(path: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "fichero_server.security.real_data_guard", str(path)],
                              env=env, capture_output=True, text=True)

    refused = run(home / "Fichero")
    assert refused.returncode != 0 and "Refusing to start" in refused.stderr
    assert run(home / "Fichero Dev Test" / "state").returncode == 0


#: A file that mentions how an engine starts but does not start one a dev can point at real data, with why.
NOT_A_STARTER = {
    "fichero-server/scripts/bundle_python_backend.sh": "packages start_backend.py into the app bundle; the bundled engine is the app's",
    "scripts/dev.sh": "prints which launcher to run",
    "scripts/check_tcp_transport_wrapper.py": "a static check of the app wrapper, starts nothing",
    "scripts/verify_workflows.sh": "runs verify_workflows.py",
    "scripts/verify_workflows.py": "boots on a disposable temp state it makes itself",
    "scripts/verify_python.sh": "boots on a base path from mktemp -d",
    "fichero-server/scripts/test_engine_harness.py": "boots on its own temp dir",
    "fichero-server/scripts/start_tailscale_backend.sh": "execs start_fichero_server.sh, which is guarded",
}
STARTS_AN_ENGINE = re.compile(r"uvicorn|[\"' ]-m[\"',]* *[\"']?fichero_server|start_backend|fichero_server\.api\.\w+:app")


def _launchers() -> list[str]:
    found = []
    for folder in ("scripts", "fichero-server/scripts", "fichero-server/bin"):
        for path in sorted((REPO / folder).rglob("*")):
            if path.is_file() and path.suffix in {".sh", ".py"} and "__pycache__" not in path.parts:
                if STARTS_AN_ENGINE.search(path.read_text(encoding="utf-8", errors="ignore")):
                    found.append(str(path.relative_to(REPO)))
    return found


#: A line that RUNS the guard: a call to refuse_real_base, or `-m fichero_server.security.real_data_guard`.
GUARD_CALL = re.compile(r"refuse_real_base\(|-m\s+fichero_server\.security\.real_data_guard")


def calls_the_guard(text: str) -> bool:
    """True when an uncommented line runs the guard: a mention in a comment or a string of prose is not a call."""
    return any(GUARD_CALL.search(line) for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_a_comment_that_names_the_guard_is_not_a_call() -> None:
    assert not calls_the_guard("# refuse_real_base(base)  # TODO\n# python -m fichero_server.security.real_data_guard x\n")
    assert not calls_the_guard("    # -m fichero_server.security.real_data_guard \"$BASE\"\nuvicorn app\n")
    assert calls_the_guard("    refuse_real_base(os.environ.get('X'))\n")
    assert calls_the_guard('PYTHONPATH=x "$PY" -m fichero_server.security.real_data_guard "$BASE" || exit 1\n')


def test_every_script_that_starts_an_engine_calls_the_guard_or_is_listed_with_why() -> None:
    """A new launcher fails here until it calls the guard (or is added to NOT_A_STARTER, in review)."""
    missing = [f for f in _launchers() if f not in NOT_A_STARTER
               and not calls_the_guard((REPO / f).read_text(encoding="utf-8"))]
    assert missing == [], f"these start an engine without the real-data guard: {missing}"


def test_the_list_of_exceptions_holds_no_stale_entry_and_no_guarded_launcher() -> None:
    launchers = _launchers()
    for name in NOT_A_STARTER:
        assert name in launchers, f"{name} no longer mentions an engine start: remove it from the list"
        assert not calls_the_guard((REPO / name).read_text(encoding="utf-8"))


def sets_the_switch(text: str) -> bool:
    """True when a line other than a comment or an `echo` (the --help text) names the owner's switch at all: an
    export, an env prefix, os.environ["..."] = "1", setdefault, an env={...} dict or a --env flag all name it."""
    return any(guard.ALLOW_REAL_STATE_ENV in line for line in text.splitlines()
               if not line.lstrip().startswith(("#", "echo ")))


def test_the_switch_check_sees_every_way_to_set_it() -> None:
    for line in ('export FICHERO_ALLOW_REAL_STATE=1', 'FICHERO_ALLOW_REAL_STATE=1 python x.py',
                 'os.environ["FICHERO_ALLOW_REAL_STATE"] = "1"', 'os.environ.setdefault("FICHERO_ALLOW_REAL_STATE", "1")',
                 'env = {"FICHERO_ALLOW_REAL_STATE": "1"}', 'subprocess.run(cmd, env={**os.environ, "FICHERO_ALLOW_REAL_STATE": "1"})'):
        assert sets_the_switch(line), line
    assert not sets_the_switch('# FICHERO_ALLOW_REAL_STATE=1 is the owner\'s\n  echo "FICHERO_ALLOW_REAL_STATE=1 set by hand."')


def test_no_script_sets_the_owners_switch() -> None:
    for folder in ("scripts", "fichero-server/scripts", "fichero-server/bin"):
        for path in (REPO / folder).rglob("*"):
            if path.is_file() and path.suffix in {".sh", ".py"} and "__pycache__" not in path.parts:
                assert not sets_the_switch(path.read_text(encoding="utf-8", errors="ignore")), f"{path} names the switch"
