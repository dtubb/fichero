from __future__ import annotations

import importlib.util
import os
import shutil
from types import SimpleNamespace
from pathlib import Path


def _load_conftest_module():
    conftest_path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location(
        "fichero_engine_tests_conftest",
        conftest_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_test_base_path_is_per_process_and_unique() -> None:
    conftest = _load_conftest_module()
    path1 = conftest._make_test_base_path()
    path2 = conftest._make_test_base_path()

    try:
        assert path1 != path2
        assert str(os.getpid()) in path1.name
        assert str(os.getpid()) in path2.name
        assert path1.exists()
        assert path2.exists()
    finally:
        shutil.rmtree(path1, ignore_errors=True)
        shutil.rmtree(path2, ignore_errors=True)


def test_deadlock_dump_timeout_parses_positive_seconds(monkeypatch) -> None:
    conftest = _load_conftest_module()
    monkeypatch.setenv("FICHERO_TEST_DEADLOCK_TIMEOUT", "420.5")

    assert conftest._deadlock_dump_timeout_seconds() == 420.5


def test_deadlock_dump_timeout_rejects_blank_invalid_and_non_positive(monkeypatch) -> None:
    conftest = _load_conftest_module()

    monkeypatch.delenv("FICHERO_TEST_DEADLOCK_TIMEOUT", raising=False)
    assert conftest._deadlock_dump_timeout_seconds() is None

    monkeypatch.setenv("FICHERO_TEST_DEADLOCK_TIMEOUT", "nope")
    assert conftest._deadlock_dump_timeout_seconds() is None

    monkeypatch.setenv("FICHERO_TEST_DEADLOCK_TIMEOUT", "0")
    assert conftest._deadlock_dump_timeout_seconds() is None

    monkeypatch.setenv("FICHERO_TEST_DEADLOCK_TIMEOUT", "-5")
    assert conftest._deadlock_dump_timeout_seconds() is None


def test_pytest_sessionstart_arms_faulthandler_when_timeout_enabled(monkeypatch) -> None:
    conftest = _load_conftest_module()
    calls: list[tuple[str, object]] = []

    monkeypatch.setenv("FICHERO_TEST_DEADLOCK_TIMEOUT", "300")
    monkeypatch.setattr(
        conftest,
        "faulthandler",
        SimpleNamespace(
            is_enabled=lambda: False,
            enable=lambda *, all_threads: calls.append(("enable", all_threads)),
            dump_traceback_later=lambda timeout, *, repeat: calls.append(
                ("dump", (timeout, repeat))
            ),
            cancel_dump_traceback_later=lambda: calls.append(("cancel", None)),
        ),
    )

    conftest.pytest_sessionstart(session=None)

    assert calls == [
        ("enable", True),
        ("dump", (300.0, False)),
    ]
    assert conftest._deadlock_dump_armed is True


def test_pytest_sessionstart_noops_without_timeout(monkeypatch) -> None:
    conftest = _load_conftest_module()
    calls: list[str] = []

    monkeypatch.delenv("FICHERO_TEST_DEADLOCK_TIMEOUT", raising=False)
    monkeypatch.setattr(
        conftest,
        "faulthandler",
        SimpleNamespace(
            is_enabled=lambda: True,
            enable=lambda *, all_threads: calls.append("enable"),
            dump_traceback_later=lambda timeout, *, repeat: calls.append("dump"),
            cancel_dump_traceback_later=lambda: calls.append("cancel"),
        ),
    )

    conftest.pytest_sessionstart(session=None)

    assert calls == []
    assert conftest._deadlock_dump_armed is False


def test_pytest_sessionfinish_cancels_only_when_armed(monkeypatch) -> None:
    # sessionfinish is ONE hook since the 2026-08-02 shadowing fix: cancel
    # first, then the perf-ratchet flush. This test covers the cancel, so the
    # ratchet must be pinned OFF — under the gate's FICHERO_PERF_RATCHET=1
    # the flush would run against session=None and fail for reasons that
    # have nothing to do with the property under test.
    monkeypatch.delenv("FICHERO_PERF_RATCHET", raising=False)
    conftest = _load_conftest_module()
    calls: list[str] = []

    monkeypatch.setattr(
        conftest,
        "faulthandler",
        SimpleNamespace(
            cancel_dump_traceback_later=lambda: calls.append("cancel"),
        ),
    )

    conftest._deadlock_dump_armed = False
    conftest.pytest_sessionfinish(session=None, exitstatus=0)
    assert calls == []

    conftest._deadlock_dump_armed = True
    conftest.pytest_sessionfinish(session=None, exitstatus=0)
    assert calls == ["cancel"]
    assert conftest._deadlock_dump_armed is False


def test_apple_marker_skips_when_capability_absent(monkeypatch) -> None:
    """The revived marker path must be SHOWN to fire (#4487).

    The requires_apple_* skip logic was dead for weeks inside a shadowed
    pytest_collection_modifyitems, over a population of zero marked tests —
    two defects concealing each other. Now that both are alive (the SVO live
    test is the first subscriber), prove the mechanism itself: an item
    carrying the keyword gets a skip marker when the probe is False, and no
    marker when the probe is True.
    """
    conftest = _load_conftest_module()

    class _Item:
        def __init__(self, keywords):
            self.keywords = keywords
            self.markers = []
            self.obj = None
            self.nodeid = "stub::test"  # read by the known-spec xfail pass

        def add_marker(self, marker):
            self.markers.append(marker)

    monkeypatch.setattr(conftest, "_APPLE_INTELLIGENCE_OK", False)
    monkeypatch.setattr(conftest, "_APPLE_VISION_OK", True)
    marked = _Item({"requires_apple_intelligence": True})
    unmarked = _Item({})
    conftest.pytest_collection_modifyitems(config=None, items=[marked, unmarked])
    assert any(m.name == "skip" for m in marked.markers), (
        "requires_apple_intelligence did not skip with the probe False — "
        "the marker mechanism is dead again"
    )
    assert not unmarked.markers, "an unmarked test acquired a marker"

    monkeypatch.setattr(conftest, "_APPLE_INTELLIGENCE_OK", True)
    available = _Item({"requires_apple_intelligence": True})
    conftest.pytest_collection_modifyitems(config=None, items=[available])
    assert not any(m.name == "skip" for m in available.markers), (
        "the marker skipped even though the capability is PRESENT — "
        "over-skipping hides a runnable test"
    )
