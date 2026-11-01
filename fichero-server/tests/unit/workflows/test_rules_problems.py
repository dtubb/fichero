"""one rules check shared by start, ladder and land (review 4 B5): a rules file the start refuses never lands."""

from __future__ import annotations

import pytest

from fichero_server.workflows import check_tool as C
from fichero_server.workflows import jail as J

GOOD = """
[check]
python = "/bin/sh"
ready = ["x.sh"]
guard_glob = "scripts/check_*.py"
min_guards = 1
contract_guards = ["scripts/check_a.py"]
check_paths = ["scripts/"]
contract_paths = ["src/"]
pytest_config = "pyproject.toml"
[jail]
user = "u"
deny_read = ["~/.ssh"]
[land]
branch = "integration"
boundary = ["x"]
"""


def _p(tmp_path, text):
    (tmp_path / "harness.toml").write_text(text)
    return C.rules_problems(tmp_path)


def test_a_complete_rules_file_has_no_problems(tmp_path):
    assert _p(tmp_path, GOOD) == []


@pytest.mark.parametrize("bad,expect", [
    (GOOD.replace('ready = ["x.sh"]\n', ""), "ready"),
    (GOOD.replace('deny_read = ["~/.ssh"]', "deny_read = []"), "deny_read"),
    (GOOD.replace("boundary =", "boundry ="), "boundry"),
    (GOOD.replace('branch = "integration"\n', ""), "branch"),
    (GOOD.replace("[jail]", "[jailx]"), "jail"),
    (GOOD.replace('check_paths = ["scripts/"]\n', ""), "check_paths"),  # review-2 H10: pinning off = fail open
    (GOOD.replace('contract_paths = ["src/"]\n', ""), "contract_paths"),
    (GOOD.replace('pytest_config = "pyproject.toml"\n', ""), "pytest_config"),
    (GOOD + '[brief]\nrulez = "x"\n', "rulez"),  # run.rules-file: a misspelt key refuses, or every brief silently loses its rules
    (GOOD + "[brief]\nrules = 3\n", "brief"),
    ("not toml [", "harness.toml"),
])
def test_each_gap_is_a_named_problem(tmp_path, bad, expect):
    assert any(expect in p for p in _p(tmp_path, bad))


def test_a_missing_file_is_a_problem(tmp_path):
    assert C.rules_problems(tmp_path)


def test_the_ladder_refuses_a_rules_file_with_problems(tmp_path):
    (tmp_path / "harness.toml").write_text(GOOD.replace("deny_read = [\"~/.ssh\"]", "deny_read = []"))
    with pytest.raises(J.JailMissing, match="deny_read"):
        C.run_ladder(tmp_path, "a", "b", tmp_path)
