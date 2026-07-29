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
    # The inspector's 10-tab bar is GONE: the Inspector IA reform (#3434/#3454,
    # b731db520) folded it into a 4-section bar plus a segmented facet sub-picker.
    # So `inspectorTabBar` / `inspectorTab-<tab>` no longer exist — do not "restore"
    # them. The hooks below are their shipped successors on the real controls.
    files = [
        ROOT / "fichero" / "fichero" / "Views" / "Inspector" / "Document" / "DocumentInspector.swift",
        # #4024: the section bar + facet picker (inspectorSectionBar/inspectorFacetPicker)
        # moved to the split extension file when DocumentInspector was split by file_length.
        ROOT / "fichero" / "fichero" / "Views" / "Inspector" / "Document" / "DocumentInspector+TabBar.swift",
        # Per-section hook is declared on the enum, not at the call site.
        ROOT / "fichero" / "fichero" / "Views" / "Inspector" / "InspectorSection.swift",
        ROOT / "fichero" / "fichero" / "Views" / "Reader" / "Knowledge" / "DocumentKGSurface.swift",
        ROOT / "fichero" / "fichero" / "Views" / "Reader" / "ReaderToolbar.swift",
        # #4024: PDF page-nav hooks (pdfPreviousPage/pdfNextPage) moved to the split
        # Controls extension file when ReaderToolbar was split by file_length.
        ROOT / "fichero" / "fichero" / "Views" / "Reader" / "ReaderToolbar+Controls.swift",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)

    # Container + per-segment hooks — the successors to inspectorTabBar and
    # inspectorTab-<tab>, so the switcher stays addressable segment by segment.
    assert '"inspectorSectionBar"' in text
    assert '"inspectorSection-\\(rawValue)"' in text
    # The sub-picker revealed by multi-facet sections (Knowledge / Notes).
    assert '"inspectorFacetPicker"' in text
    assert '"knowledgeSurfaceContent"' in text
    assert '"pdfPreviousPage"' in text
    assert '"pdfNextPage"' in text
