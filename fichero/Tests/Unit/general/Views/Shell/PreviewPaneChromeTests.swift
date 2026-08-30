@testable import Fichero
import XCTest

/// The 2026-08-29 Preview head restructure's value logic: the head ↔ canvas
/// chrome seam, the markup-tool routing split (annotation machinery vs the
/// preview-regions lane's verbs), and the highlight split-button's persisted
/// style.
@MainActor
final class PreviewPaneChromeTests: XCTestCase {

    // MARK: - Chrome seam

    func testResetClearsEverythingAPublisherWrote() {
        let chrome = PreviewPaneChrome()
        chrome.pageNav = ReaderPageNav(
            pageIndex: 2, pageCount: 9,
            canGoPrevious: true, canGoNext: true,
            goPrevious: {}, goNext: {}
        )
        chrome.renditionNames = ["Original", "Enhanced"]
        chrome.renditionIndex = 1
        chrome.selectRendition = { _ in }

        chrome.reset()

        XCTAssertNil(chrome.pageNav)
        XCTAssertTrue(chrome.renditionNames.isEmpty)
        XCTAssertEqual(chrome.renditionIndex, 0)
        XCTAssertNil(chrome.selectRendition)
    }

    // MARK: - Markup tool routing

    func testOnlyHighlightAndNoteMapToTheAnnotationMachinery() {
        // Highlight/note ride the existing AnnotationStore path; select /
        // draw-region are the preview-regions lane's; line has no drawing
        // kind yet. The split keeps the seam honest.
        XCTAssertTrue(PreviewMarkupTool.highlight.mapsToAnnotationKind)
        XCTAssertTrue(PreviewMarkupTool.note.mapsToAnnotationKind)
        XCTAssertFalse(PreviewMarkupTool.select.mapsToAnnotationKind)
        XCTAssertFalse(PreviewMarkupTool.drawRegion.mapsToAnnotationKind)
        XCTAssertFalse(PreviewMarkupTool.line.mapsToAnnotationKind)
    }

    func testMarkupToolRawValuesRoundTripThroughTheNotificationSeam() {
        for tool in PreviewMarkupTool.allCases {
            XCTAssertEqual(PreviewMarkupTool(rawValue: tool.rawValue), tool)
        }
    }

    // MARK: - Highlight split-button state

    func testColorStylesPersistHexAndModesDoNot() {
        // The engine's `validate_annotation_color` accepts ONLY #RRGGBB[AA] —
        // a color NAME would 422 the save. The five colors persist hex;
        // underline/strikethrough save uncolored until a backing kind exists.
        for style in PreviewHighlightStyle.colors {
            let hex = style.persistedColor ?? ""
            XCTAssertTrue(hex.hasPrefix("#") && hex.count == 7,
                          "\(style.rawValue) must persist #RRGGBB, got \(hex)")
            XCTAssertTrue(style.isColor)
        }
        XCTAssertNil(PreviewHighlightStyle.underline.persistedColor)
        XCTAssertNil(PreviewHighlightStyle.strikethrough.persistedColor)
        XCTAssertFalse(PreviewHighlightStyle.underline.isColor)
    }

    func testHighlightMenuOrderIsPreviewAppsFiveColors() {
        XCTAssertEqual(
            PreviewHighlightStyle.colors.map(\.rawValue),
            ["yellow", "green", "blue", "pink", "purple"]
        )
    }
}
