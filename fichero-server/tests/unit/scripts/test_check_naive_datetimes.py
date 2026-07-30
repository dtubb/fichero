"""The naive-datetime guardrail must FIRE on the shapes it claims to catch."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_naive_datetimes.py"
_SPEC = importlib.util.spec_from_file_location("check_naive_datetimes", _SCRIPT)
assert _SPEC and _SPEC.loader
check_naive_datetimes = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_naive_datetimes  # so @dataclass resolves its module
_SPEC.loader.exec_module(check_naive_datetimes)  # type: ignore[attr-defined]


def _scan(source: str):
    return check_naive_datetimes._scan_source("probe.py", source)


# ---------------------------------------------------------------------------
# The rule fires
# ---------------------------------------------------------------------------

FIRING = {
    "plain now": "from datetime import datetime\nx = datetime.now()\n",
    "utcnow": "from datetime import datetime\nx = datetime.utcnow()\n",
    "module attribute form": "import datetime\nx = datetime.datetime.now()\n",
    "aliased class": "from datetime import datetime as _dt\nx = _dt.now()\n",
    "aliased module": "import datetime as dt\nx = dt.datetime.utcnow()\n",
    "pydantic default_factory": (
        "from datetime import datetime\nfrom pydantic import Field\n"
        "y = Field(default_factory=datetime.now)\n"
    ),
    "dataclass default_factory": (
        "from datetime import datetime\nfrom dataclasses import field\n"
        "y = field(default_factory=datetime.utcnow)\n"
    ),
    "lambda wrapper": "from datetime import datetime\nf = lambda: datetime.now()\n",
    "inside an f-string": (
        'from datetime import datetime\ns = f"{datetime.now().isoformat()}"\n'
    ),
    "inside arithmetic": (
        "from datetime import datetime, timedelta\n"
        "x = datetime.now() - timedelta(hours=24)\n"
    ),
    "nested in a call argument": (
        "from datetime import datetime\nprint(str(datetime.now()))\n"
    ),
    "inside a method body": (
        "from datetime import datetime\n"
        "class C:\n    def f(self):\n        return datetime.now()\n"
    ),
}


@pytest.mark.parametrize("label", sorted(FIRING))
def test_rule_fires(label: str) -> None:
    found = _scan(FIRING[label])
    assert found, f"guardrail failed to fire on {label}"


# ---------------------------------------------------------------------------
# The rule does not fire
# ---------------------------------------------------------------------------

PASSING = {
    "aware utc positional": (
        "from datetime import datetime, timezone\nx = datetime.now(timezone.utc)\n"
    ),
    "aware utc keyword": (
        "from datetime import datetime, timezone\nx = datetime.now(tz=timezone.utc)\n"
    ),
    "zoneinfo": (
        "from datetime import datetime\nfrom zoneinfo import ZoneInfo\n"
        "x = datetime.now(ZoneInfo('UTC'))\n"
    ),
    "module form with tz": (
        "import datetime\nx = datetime.datetime.now(datetime.timezone.utc)\n"
    ),
    "sanctioned helper": (
        "from fichero_server.core.timeutil import utc_now\nx = utc_now()\n"
    ),
    "helper as default_factory": (
        "from fichero_server.core.timeutil import utc_now\nfrom pydantic import Field\n"
        "y = Field(default_factory=utc_now)\n"
    ),
    "unrelated now attribute": (
        "from datetime import datetime\nclass C:\n    now = 1\nx = C.now\n"
    ),
    "unrelated object's now method": (
        "from datetime import datetime\nx = pendulum.now()\n"
    ),
    "no datetime import at all": "x = something.now()\n",
    "mention in a comment": (
        "from datetime import datetime\n# never call datetime.now() here\nx = 1\n"
    ),
    "mention in a docstring": (
        'from datetime import datetime\n"""Never call datetime.utcnow()."""\nx = 1\n'
    ),
    "mention in a string literal": (
        'from datetime import datetime\nmsg = "use datetime.now() ... do not"\n'
    ),
}


@pytest.mark.parametrize("label", sorted(PASSING))
def test_rule_does_not_fire(label: str) -> None:
    found = _scan(PASSING[label])
    assert not found, f"guardrail wrongly fired on {label}: {[str(f) for f in found]}"


# ---------------------------------------------------------------------------
# Reporting + escape hatch + real-tree state
# ---------------------------------------------------------------------------


def test_offender_reports_path_and_line() -> None:
    found = check_naive_datetimes._scan_source(
        "fichero-server/src/fichero_server/x.py",
        "from datetime import datetime\n\n\nv = datetime.now()\n",
    )
    assert [f.key for f in found] == ["fichero-server/src/fichero_server/x.py:4"]
    assert "datetime.now()" in str(found[0])


def test_each_offending_line_is_reported_once() -> None:
    found = _scan("from datetime import datetime\nx = datetime.now()\n")
    assert len(found) == 1, [str(f) for f in found]


def test_two_offenders_on_separate_lines_are_both_reported() -> None:
    found = _scan(
        "from datetime import datetime\nx = datetime.now()\ny = datetime.utcnow()\n"
    )
    assert [f.line for f in found] == [2, 3]


def test_allow_comment_suppresses_exactly_its_own_line() -> None:
    allow = check_naive_datetimes.ALLOW_COMMENT
    found = _scan(
        "from datetime import datetime\n"
        f"x = datetime.now()  # {allow}\n"
        "y = datetime.now()\n"
    )
    assert [f.line for f in found] == [3]


def test_syntax_error_does_not_crash_the_scan() -> None:
    assert _scan("from datetime import datetime\ndef broken(:\n") == []


def test_self_test_passes() -> None:
    check_naive_datetimes._self_test()


def test_script_entrypoint_is_green_on_the_real_tree() -> None:
    """The sweep is complete: no offenders and no stale baseline entries."""
    assert check_naive_datetimes.main([]) == 0


def test_baseline_has_no_stale_entries() -> None:
    found_keys = {o.key for o in check_naive_datetimes.offenders()}
    stale = sorted(
        k for k in check_naive_datetimes.KNOWN_VIOLATIONS if k not in found_keys
    )
    assert stale == [], f"stale KNOWN_VIOLATIONS entries: {stale}"


def test_timeutil_is_the_only_sanctioned_file() -> None:
    assert check_naive_datetimes.SANCTIONED_FILES == {
        "fichero-server/src/fichero_server/core/timeutil.py"
    }
