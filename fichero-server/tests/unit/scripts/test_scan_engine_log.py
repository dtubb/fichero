"""`scripts/scan_engine_log.py` fails a log in which a WARNING-or-worse template repeats past a ceiling
(`engine.silent.scan-script`). The fixture is the real shape of the Air's 380,611-line embedding warning."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts/scan_engine_log.py"
LOGS = ROOT / "fichero-server/tests/fixtures/engine_logs"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


def test_the_embedding_flood_fails_and_is_named():
    result = _run(str(LOGS / "embedding_380k.log"))
    assert result.returncode == 1, result.stdout
    assert "Failed to create embedding for <hex>" in result.stdout
    assert "60" in result.stdout


def test_info_lines_are_not_counted():
    assert "poll activity.list_background_jobs" not in _run(str(LOGS / "embedding_380k.log")).stdout


def test_an_allowed_template_passes():
    result = _run(str(LOGS / "embedding_380k.log"), "--allow", "Failed to create embedding", "--allow", "change-hub")
    assert result.returncode == 0, result.stdout


def test_a_clean_log_passes():
    assert _run(str(LOGS / "clean.log")).returncode == 0


def test_a_missing_file_is_exit_2():
    assert _run(str(LOGS / "nope.log")).returncode == 2


def test_a_file_that_is_not_a_log_is_exit_2(tmp_path):
    binary = tmp_path / "x.log"
    binary.write_bytes(b"\x00\x01\x02not a log\n" * 10)
    assert _run(str(binary)).returncode == 2


def test_normalise_gives_one_template_for_two_ids():
    spec = importlib.util.spec_from_file_location("scan_engine_log", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    one = module.normalise("Failed to create embedding for 71470c7dc13a4b93b769366ed70dd488: x 12")
    two = module.normalise("Failed to create embedding for 4e7e7a018c66422699f9846522329cb0: x 99")
    assert one == two


def _log(path, written: int, held: int) -> str:
    """A log shaped like core/log_throttle's output: `written` real lines, then one raw-template summary of `held`."""
    lines = [
        f"2026-10-30 10:00:{i % 60:02d},000 - fichero_server.db - WARNING - Failed to create embedding for "
        f"{i:032x}: The search model stopped; try again later."
        for i in range(written)
    ]
    lines.append(
        "2026-10-30 10:01:01,000 - fichero_server.db - WARNING - Failed to create embedding for %s: %s"
        f" — repeated {held} times in the last minute"
    )
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def test_a_collapsed_summary_is_added_to_the_template_it_stands_for(tmp_path):
    result = _run(str(LOGS / "embedding_collapsed.log"), "--ceiling", "100")
    assert result.returncode == 1
    assert "6005" in result.stdout and len(result.stdout.splitlines()) == 1, result.stdout


def test_written_plus_held_over_the_ceiling_is_exit_1_not_clean(tmp_path):
    over = _run(_log(tmp_path / "a.log", 45, 9))  # 54 > 50, but each half alone is not
    assert over.returncode == 1 and " 54 " in over.stdout, over.stdout
    assert _run(_log(tmp_path / "b.log", 45, 5)).returncode == 0  # 50 is not "more than 50"


def test_an_allow_regex_naming_the_cause_covers_the_summary_too(tmp_path):
    assert _run(_log(tmp_path / "c.log", 5, 6000), "--allow", "search model stopped").returncode == 0


def test_a_bad_allow_regex_is_exit_2_not_1():
    result = _run(str(LOGS / "clean.log"), "--allow", "(")
    assert result.returncode == 2 and "Traceback" not in result.stderr, result.stderr


def test_a_non_utf8_byte_under_an_ascii_stdout_does_not_crash(tmp_path):
    log = tmp_path / "x.log"
    line = "2026-10-30 10:00:00,000 - fichero_server.db - WARNING - bad \xe9 byte\n"
    log.write_bytes(("\n".join([line.rstrip("\n")] * 60) + "\n").encode("latin-1"))
    import os

    env = {**os.environ, "PYTHONIOENCODING": "ascii"}
    result = subprocess.run([sys.executable, str(SCRIPT), str(log)], capture_output=True, text=True, env=env, check=False)
    assert result.returncode == 1 and "Traceback" not in result.stderr, result.stderr


def test_a_log_mostly_in_another_format_is_exit_2_not_clean(tmp_path):
    log = tmp_path / "x.log"
    other = "2026-10-30T10:00:00Z WARNING db Failed to create embedding\n" * 1000
    log.write_text("2026-10-30 10:00:00,000 - fichero_server.db - WARNING - once\n" + other)
    result = _run(str(log))
    assert result.returncode == 2 and "1000 lines miss" in result.stderr, (result.returncode, result.stderr)


def _module():
    spec = importlib.util.spec_from_file_location("scan_engine_log", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paths_with_spaces_are_one_template_and_leave_no_words():
    m = _module()
    one = m.normalise("Missing original path='/Vol/Some Folder/Sub Folder 12/a b.tif'")
    two = m.normalise("Missing original path='/Other/Shorter/x.tif'")
    assert one == two == "Missing original path='<path>'"
    unquoted = m.normalise("failed for item 7: File not found: /Vol/Some Folder/b 3.tif")
    assert "Folder" not in unquoted and unquoted.endswith("<path>")


def test_short_hex_ids_are_one_template_but_plain_words_survive():
    m = _module()
    assert m.normalise("lost 1a2b3c4d now") == m.normalise("lost 9f8e7d6c now")
    assert m.normalise("a decade and defaced") == "a decade and defaced"


def test_rotated_logs_are_summed(tmp_path):
    one, two = tmp_path / "engine.log", tmp_path / "engine.log.1"
    for path in (one, two):
        path.write_text(
            "2026-10-30 10:00:00,000 - fichero_server.db - WARNING - Same problem 7\n" * 30
        )
    assert _run(str(one)).returncode == 0
    both = _run(str(one), str(two))
    assert both.returncode == 1 and " 60 " in both.stdout, both.stdout


def _lines(logger: str, level: str, message: str, n: int = 1, second: int = 0) -> str:
    return "".join(
        f"2026-10-30 10:00:{second:02d},000 - {logger} - {level} - {message}\n" for _ in range(n)
    )


def test_an_allow_on_one_cause_does_not_hide_a_summary_that_may_belong_to_another(tmp_path):
    log = tmp_path / "a.log"
    log.write_text(
        _lines("fichero_server.db", "WARNING", "Failed for X: model is being fetched", 20)
        + _lines("fichero_server.db", "WARNING", "Failed for X: disk corrupted", 10)
        + _lines("fichero_server.db", "WARNING", "Failed for %s: %s — repeated 6000 times in the last minute")
    )
    assert _run(str(log), "--allow", "being fetched").returncode == 1
    assert _run(str(log), "--allow", "Failed for").returncode == 0  # all of them allowed


def test_a_summary_from_another_logger_is_not_folded_into_an_allowed_template(tmp_path):
    log = tmp_path / "a.log"
    log.write_text(
        _lines("fichero_server.db", "WARNING", "Failed for X: fetched", 5)
        + _lines("fichero_server.other", "WARNING", "Failed for %s: %s — repeated 6000 times in the last minute")
    )
    assert _run(str(log), "--allow", "fetched").returncode == 1


def test_other_format_specs_and_an_unquoted_path_tail_still_match_the_summary(tmp_path):
    for raw, written in (
        ("Took %.1f s for %s", "Took 1.5 s for doc"),
        ("Row %i bad", "Row 7 bad"),
        ("File not found: %s (doc %s)", "File not found: /Some Dir/a b.tif (doc 4)"),
    ):
        log = tmp_path / "a.log"
        log.write_text(
            _lines("fichero_server.db", "WARNING", written, 45)
            + _lines("fichero_server.db", "WARNING", f"{raw} — repeated 9 times in the last minute")
        )
        result = _run(str(log))
        assert result.returncode == 1 and " 54 " in result.stdout, (raw, result.stdout)


def test_a_log_in_a_different_severity_format_is_exit_2(tmp_path):
    log = tmp_path / "a.log"
    log.write_text(_lines("fichero_server.db", "INFO", "up", 1000) + "WARNING:  fichero_server.db: failed\n" * 900)
    assert _run(str(log)).returncode == 2
    other = tmp_path / "b.log"
    other.write_text(_lines("fichero_server.db", "INFO", "up") + "WARNING:  fichero_server.db: failed\n" * 1000)
    assert _run(str(other)).returncode == 2


def test_uppercase_ids_starting_with_a_letter_are_one_template():
    m = _module()
    assert m.normalise("bad id " + "A" * 31 + "F now") == m.normalise("bad id " + "B" * 31 + "C now")
    assert m.normalise("lost 1A2B3C4D now") == m.normalise("lost 9F8E7D6C now")


def test_prose_with_a_slash_is_not_a_path():
    m = _module()
    assert m.normalise("Retry 1 / 3: model crashed") == "Retry <n> / <n>: model crashed"


def test_an_empty_rotated_partner_is_skipped_not_an_error(tmp_path):
    empty, full = tmp_path / "engine.log", tmp_path / "engine.log.1"
    empty.write_text("")
    full.write_text(_lines("fichero_server.db", "WARNING", "same 7", 60))
    assert _run(str(empty), str(full)).returncode == 1
    assert _run(str(empty)).returncode == 2
