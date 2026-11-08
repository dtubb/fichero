"""2026-11-08 (review 130): [check.whole_tests] values became lists of test files; verify-all put them in a set and died."""
from pathlib import Path

from fichero_builder import check_tool, verify

ROOT = Path(__file__).resolve().parents[2]


def test_verify_takes_only_the_dir_values_as_whole_suites_and_reads_the_real_rules(tmp_path):
    for d in ("fichero-builder/tests", "fichero-server/tests"):
        (tmp_path / d).mkdir(parents=True)
    cfg = check_tool.Config(whole_tests={"fichero-builder/fichero_builder/": "fichero-builder/tests",
                                         "fichero-server/src/": ["fichero-server/tests/unit/scripts/test_db_access_guardrail.py"]})
    dirs, whole = verify._suite_dirs(tmp_path, cfg)
    assert whole == ("fichero-builder/tests",) and dirs == ["fichero-server/tests"]
    verify._suite_dirs(ROOT, check_tool.load(ROOT))  # the repo's own harness.toml, lists and all, never raises


def test_daily_builds_runs_the_daily_tests_on_the_checkout_and_a_red_names_its_first_failed_test(tmp_path, monkeypatch, capsys):
    """2026-11-08: every tree-scanning guardrail test once a day; exit 1 on red with the FAILED line, 0 on green, even with no build remote."""
    from fichero_builder import __main__ as cli
    cfg = check_tool.Config(daily_tests=("fichero-server/tests/unit/scripts/test_db_access_guardrail.py",))
    monkeypatch.setattr(check_tool, "load", lambda root: cfg)
    seen = []
    red = {"ok": False, "stdout_tail": "x\nFAILED fichero-server/tests/unit/scripts/test_db_access_guardrail.py::test_no_new\n1 failed"}
    monkeypatch.setattr(check_tool, "green_runs", lambda tree, files, whole, c, t: (seen.append(files), red)[1])
    assert cli.main(["daily-builds", "--root", str(tmp_path), "--state", str(tmp_path / "s")]) == 1
    assert seen == [list(cfg.daily_tests)]
    assert "scan-tests: RED FAILED fichero-server/tests/unit/scripts/test_db_access_guardrail.py::test_no_new" in capsys.readouterr().out
    monkeypatch.setattr(check_tool, "green_runs", lambda *a: {"ok": True, "stdout_tail": "1 passed"})
    assert cli.main(["daily-builds", "--root", str(tmp_path), "--state", str(tmp_path / "s")]) == 0
    assert "scan-tests: GREEN" in capsys.readouterr().out
