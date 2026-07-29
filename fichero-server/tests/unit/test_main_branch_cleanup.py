from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_engine_harness_no_longer_hardcodes_002_checkout():
    harness = REPO_ROOT / "fichero_server" / "fichero-tests" / "EngineHarness.swift"
    text = harness.read_text()

    assert "fichero-0.0.2" not in text
    # Checkout-agnostic discovery (#2657): the harness walks up from `#filePath`,
    # so it finds the repo regardless of the checkout directory name (superseding
    # the earlier ~/code/fichero-worktrees name-scan).
    assert "#filePath" in text
