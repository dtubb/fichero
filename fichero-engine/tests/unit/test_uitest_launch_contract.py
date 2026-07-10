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


def test_reading_surface_has_stable_accessibility_hooks() -> None:
    files = [
        ROOT / "fichero" / "fichero" / "Views" / "Library" / "DocumentInspector" / "DocumentInspector.swift",
        ROOT / "fichero" / "fichero" / "Views" / "Library" / "DocumentKGSurface.swift",
        ROOT / "fichero" / "fichero" / "Views" / "Toolbars" / "ReaderToolbar.swift",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert '"inspectorTabBar"' in text
    assert '"inspectorTab-\\(tab.rawValue)"' in text
    assert '"knowledgeSurfaceContent"' in text
    assert '"pdfPreviousPage"' in text
    assert '"pdfNextPage"' in text
