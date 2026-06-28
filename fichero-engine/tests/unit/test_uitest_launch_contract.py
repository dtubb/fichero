"""Source-contract guard for the future XCUITest target (#1230)."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_ui_test_launch_uses_isolated_library_hooks() -> None:
    support = ROOT / "fichero" / "fichero" / "Services" / "UITestSupport.swift"
    app = ROOT / "fichero" / "fichero" / "FicheroApp.swift"

    support_text = support.read_text(encoding="utf-8")
    app_text = app.read_text(encoding="utf-8")

    assert "--uitesting" in support_text
    assert "FICHERO_UITEST_HOME" in support_text
    assert "--fichero-library" in support_text
    assert "FICHERO_UITEST_LIBRARY" in support_text
    assert "openUITestLibraryOverrideIfNeeded()" in app_text
