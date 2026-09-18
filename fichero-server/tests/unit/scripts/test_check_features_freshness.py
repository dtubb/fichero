"""Pins `testenv.gate-source` (spec: test-environment-contract): `features.yaml` is the
tier source, and `check_features_freshness.py` actually catches generated artifacts that
have drifted from it — not just a script that always prints OK.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
import check_features_freshness  # noqa: E402


def test_repo_is_currently_fresh():
    """The real repo's generated feature-tier files must already match features.yaml —
    if this fails, someone edited features.yaml without regenerating."""
    assert check_features_freshness.check_repo() == 0


def test_self_check_catches_injected_drift():
    """The guardrail's own proof: it must detect a deliberately-drifted generated file,
    not pass vacuously."""
    assert check_features_freshness.self_check() == 0
