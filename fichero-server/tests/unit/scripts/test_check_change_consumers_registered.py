"""A `ChangeEventConsumer` that nothing registers is dead code (#4954).

A store can conform to the protocol, implement `apply` and `resync` correctly, be covered
by passing tests — and never run, because nothing handed it to
`LibraryChangeStream.register`. The tests still pass: a unit test constructs the store
itself, so it never asks whether the app does.

That is exactly what happened. `SegmentStore`'s conformance was committed with tests and
was dead code — neither it nor `SegmentService` was constructed anywhere, so grepping for
`SegmentStore` outside its own two model files returned two comments. The lane found it by
wiring, and wrote down why nothing helped: "no guard asks whether a registered consumer
exists for a domain the engine emits."

`test_it_would_have_caught_the_dead_store` is the load-bearing test here. A guard written
after the fact, against a tree where the bug is already fixed, proves nothing by passing —
so that test runs the detector against `LibraryManager.swift` AS IT WAS before the fix and
asserts it fails. Without it this file would be a green guard nobody knows the value of.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = _ROOT / "scripts" / "check_change_consumers_registered.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_change_consumers_registered", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)  # type: ignore[attr-defined]

#: The commit that constructed the store and registered it. Its parent is the tree where
#: the conformance existed and was unreachable.
FIX_COMMIT = "7c752e9ab"


class TestItWouldHaveCaughtTheRealBug:
    def test_it_would_have_caught_the_dead_store(self):
        """Against the registrar as it was BEFORE the fix, SegmentStore is unregistered.

        This is the only evidence that the guard is worth having. Passing on a fixed tree
        is not evidence of anything.
        """
        before = subprocess.run(
            ["git", "show", f"{FIX_COMMIT}^:fichero/fichero/Models/LibraryManager.swift"],
            cwd=_ROOT, capture_output=True, text=True, check=False,
        )
        if before.returncode != 0:
            import pytest

            pytest.skip(f"{FIX_COMMIT}^ not in this clone's history")

        mentioned = guard.registered_names(before.stdout)
        assert "SegmentStore" not in mentioned, "the premise moved: it WAS registered before"
        # and the ones that were fine stay fine, so the check is not simply always-fail
        for already_wired in ("ArtifactEntityStore", "SearchStore", "WorkflowStore"):
            assert already_wired in mentioned, already_wired


class TestWhatCountsAsAConformance:
    def test_both_declaration_forms(self):
        assert guard._CONFORMER.findall("final class A: ChangeEventConsumer {") == ["A"]
        assert guard._CONFORMER.findall("extension B: ChangeEventConsumer {") == ["B"]

    def test_a_conformance_among_others(self):
        assert guard._CONFORMER.findall("final class C: Observable, ChangeEventConsumer {") == ["C"]

    def test_a_longer_protocol_name_is_not_this_one(self):
        assert guard._CONFORMER.findall("final class D: ChangeEventConsumerish {") == []

    def test_prose_about_a_conformance_is_not_one(self):
        """Third guard in two days where prose counted as code, so it is tested here."""
        assert guard._CONFORMER.findall(guard.code_only("// final class E: ChangeEventConsumer {")) == []
        assert guard._CONFORMER.findall(guard.code_only("/* extension F: ChangeEventConsumer */")) == []


class TestWhatCountsAsRegistered:
    def test_a_type_named_on_a_property_declaration_counts(self):
        """Most stores register as `self.documentStore`, so the TYPE appears only here."""
        assert "DocumentStore" in guard.registered_names("var documentStore: DocumentStore")

    def test_a_type_named_in_the_register_call_counts(self):
        assert "SegmentStore" in guard.registered_names("stream.register(SegmentStore.shared(for: s))")

    def test_a_type_named_only_in_a_comment_does_not(self):
        assert "Ghost" not in guard.registered_names("// Ghost was removed 2026-01-01")


class TestTheTreeAndTheBlindPath:
    def test_every_consumer_is_registered_today(self):
        assert guard.scan() == {}

    def test_it_sees_the_consumers_that_exist(self):
        """If this collapses the guard has gone blind and would pass on anything."""
        found = guard.conformers()
        assert len(found) >= 5, found
        assert "SegmentStore" in found

    def test_the_registrar_is_a_real_file(self):
        """A moved registrar must be BLIND and loud (#4382), not report every consumer
        as unregistered — which would be a wall of false failures at the worst moment."""
        assert guard.REGISTRAR.exists(), guard.REGISTRAR

    def test_the_guard_exits_zero_on_the_repo(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_change_consumers_registered.py"],
            cwd=_ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
