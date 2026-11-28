"""The build rung's remote path (#6589): the runner's real directory (`pwd -P`), every use of it quoted for the remote shell, the
rsync told to protect its arguments, and one alert when the remote build env-reds three times in a row."""
import shlex

from fichero_builder import check_tool, journal

LOGICAL = "/Users/Shared/gate-link"
REAL = "/Volumes/Ext Disk/fichero gate"  # the symlink's target: a space in a volume name and in a folder name
BUILD = ("xcodebuild", "-scheme", "S", "-derivedDataPath", "x", "build")


def _cfg():
    return check_tool.Config(build=BUILD, build_remote=f"imac:{LOGICAL}")


class Fake:
    """A fake ssh and run_command that record what they were asked; `red` is the stderr of a build that exits 1 (None = green)."""

    def __init__(self, monkeypatch, tmp_path, red=None):
        self.ssh_scripts, self.argvs, self.red = [], [], red
        monkeypatch.setattr(journal, "STATE", tmp_path / "state")
        monkeypatch.setattr(check_tool, "_stable_build_tree", lambda root, cfg: str(root))
        monkeypatch.setattr(check_tool, "_ssh", self.ssh)
        monkeypatch.setattr(check_tool, "run_command", self.run)

    def ssh(self, host, script, *a, **k):
        self.ssh_scripts.append(script)
        return type("P", (), {"returncode": 0, "stdout": REAL.encode() if "pwd" in script else b"", "stderr": b""})()

    def run(self, name, argv, *a, **k):
        self.argvs.append((name, list(argv)))
        if name == "build-sync":
            return {"ok": True}
        return {"ok": self.red is None, "exit_code": 0 if self.red is None else 1, "timed_out": False, "seconds": 1,
                "stdout_tail": "", "stderr_tail": self.red or "", "errors": ""}


def test_the_real_path_with_a_space_survives_into_every_remote_command(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path)
    assert check_tool._remote_build(tmp_path, _cfg(), reuse=False)["ok"]
    assert "pwd -P" in fake.ssh_scripts[0]  # the probe asks for the physical path, so the tool sees one path, not two
    sync = dict(fake.argvs)["build-sync"]
    assert "--protect-args" not in sync and "-s" not in sync  # Apple's stock rsync (2.6.9) rejects the flag
    assert sync[-1] == f"imac:{shlex.quote(REAL + '/build-tree')}/"  # the remote shell re-splits the path, so it is quoted
    outer = shlex.split(dict(fake.argvs)["build"][-1])  # python -c <lock code> <lock file> <script>
    assert outer[0] == f"{REAL}/venv/bin/python" and outer[3] == f"{REAL}/heavy.lock"
    inner = shlex.split(outer[4])  # rm -rf <bundle> && mkdir -p <results> && cd <tree> && the build
    for part in (f"{REAL}/results/build.xcresult", f"{REAL}/results", f"{REAL}/build-tree", f"{REAL}/derived"):
        assert part in inner, part


def test_the_probe_quotes_the_configured_base_with_a_space(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path)
    cfg = check_tool.Config(build=BUILD, build_remote="imac:/Volumes/My Disk/gate")
    check_tool._remote_build(tmp_path, cfg, reuse=False)
    assert shlex.split(fake.ssh_scripts[0])[:3] == ["mkdir", "-p", "/Volumes/My Disk/gate"]


def test_three_env_reds_in_a_row_raise_one_alert_naming_the_runner_and_the_last_error(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path)
    for n in (1, 2, 3, 4):
        fake.red = f"module '_Builtin_float' is defined in both ({n})"
        assert check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)["remote_env_red"]
        alerts = [x for x in journal.read() if x.get("event") == "alert"]
        assert len(alerts) == (1 if n >= 3 else 0), n
    assert "imac" in alerts[0]["what"] and "defined in both (3)" in alerts[0]["what"]


def test_env_reds_of_earlier_ladders_count_because_the_count_is_read_from_the_journal(tmp_path, monkeypatch):
    """Each ladder is its own process: two env-reds journalled by earlier processes plus this one make three."""
    fake = Fake(monkeypatch, tmp_path, red="module defined in both")
    for _ in range(2):
        journal.append("check", state="build-remote-env-red", rung="build", runner="imac", detail="earlier process")
    check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)
    alerts = [x for x in journal.read() if x.get("event") == "alert"]
    assert len(alerts) == 1 and "imac" in alerts[0]["what"] and "module defined in both" in alerts[0]["what"]
    assert fake.argvs  # nothing in this process held the count


def test_a_build_that_ran_over_there_resets_the_count_and_another_runner_does_not_count(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, red="boom")
    journal.append("check", state="build-remote-env-red", rung="build", runner="air", detail="another runner")
    journal.append("check", state="build-remote-env-red", rung="build", runner="imac", detail="old")
    journal.append("check", state="build-remote", rung="build", runner="imac", ok=True, seconds=1)  # it ran: the old red is forgotten
    for _ in range(2):
        check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)
    assert [x for x in journal.read() if x.get("event") == "alert"] == []
    fake.red = None
    check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)
    fake.red = "boom"
    check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)
    assert [x for x in journal.read() if x.get("event") == "alert"] == []


def test_a_streak_already_longer_than_three_on_disk_alerts_once_and_not_again_in_the_same_streak(tmp_path, monkeypatch):
    Fake(monkeypatch, tmp_path, red="module defined in both")
    for _ in range(5):
        journal.append("check", state="build-remote-env-red", rung="build", runner="imac", detail="before this change")
    check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)  # the 6th red
    assert len([x for x in journal.read() if x.get("event") == "alert"]) == 1
    check_tool._remote_build_locked(tmp_path, _cfg(), "imac", REAL, (), "build", False)  # the 7th: still one alert for the streak
    assert len([x for x in journal.read() if x.get("event") == "alert"]) == 1


DEFINED_IN_BOTH = ("error: Clang dependency scanning failure: module 'Darwin' is defined in both "
                   "'/Volumes/Fichero Development/fichero-gate/derived-tests/ModuleCache.noindex/X/Darwin.pcm' and "
                   "'/Users/dtubb/fichero-gate/derived-tests/ModuleCache.noindex/Y/Darwin.pcm'")


def test_a_module_defined_in_both_gate_paths_is_a_stale_cache_and_the_verb_names_it():
    """2026-11-28 09:34 and 09:58: the daily ios-sim and tests builds said "COULD NOT RUN" with a module cache that held PCMs from
    the symlinked ~/fichero-gate beside the real /Volumes path. It is a stale cache (cleared, built once more), and the verb says
    the remote's error, not that the remote is down."""
    assert check_tool.STALE_CACHE.search(DEFINED_IN_BOTH)
    why = check_tool.env_red_why({"stdout_tail": "** BUILD FAILED **\n" + DEFINED_IN_BOTH, "stderr_tail": ""})
    assert why.startswith("error: Clang dependency scanning failure: module 'Darwin' is defined in both"), why
    assert check_tool.env_red_why({"stderr_tail": "ssh: connect timed out\nbye"}) == "bye"
