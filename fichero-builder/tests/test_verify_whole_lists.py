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


def test_every_engine_test_using_the_scan_helper_runs_daily_and_the_ones_that_scan_the_repo_run_per_batch():
    """Review 132: 17 tests loaded scripts/_scan_files.py by path and were in neither list. Any engine test that names the
    helper is in [check].daily_tests; one that scans repo paths is under a [check.whole_tests] prefix (a temp-dir-only one
    may be daily only, listed here by name)."""
    import subprocess
    if (ROOT / ".git").exists():
        found = set(subprocess.run(["git", "-C", str(ROOT), "grep", "-l", "_scan_files", "--", "fichero-server/tests/**/*.py"],
                                   capture_output=True, text=True).stdout.split())
    else:  # a gate copy (the M4 run dir) has no repo: read the tree itself
        found = {p.relative_to(ROOT).as_posix() for p in (ROOT / "fichero-server" / "tests").rglob("*.py")
                 if "_scan_files" in p.read_text(errors="replace")}
    cfg = check_tool.load(ROOT)
    assert found and not found - set(cfg.daily_tests), sorted(found - set(cfg.daily_tests))
    per_batch = {t for v in cfg.whole_tests.values() if not isinstance(v, str) for t in v}
    temp_only = {f"fichero-server/tests/unit/{t}" for t in (
        "formats/test_real_files_lose_no_text.py", "importers/test_folder_of_images_and_layout.py", "importers/test_pages_in_icloud_5669.py",
        "jobs/test_adopted_folder.py", "jobs/test_synced_folder.py", "jobs/test_synced_folder_keep_arranged.py",
        "llm/test_spacy_pipelines_as_files_to_spec.py", "transfer/test_incoming_copy_security.py",
        "transfer/test_transfer_a_page_whole.py", "transfer/test_transfer_is_never_half_done.py")}
    assert not found - per_batch - temp_only, sorted(found - per_batch - temp_only)
