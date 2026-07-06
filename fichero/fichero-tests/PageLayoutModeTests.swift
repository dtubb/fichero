@testable import Fichero
import PDFKit
import XCTest

/// Tests for PageLayoutMode (#2090) — the reading-surface page-arrangement enum
/// that unifies PDFKit's native display modes with the custom N-up grid. Pure
/// value logic: raw-value persistence contract, column counts, continuous flag,
/// and the PDFKit-native vs custom-grid partition. No live engine.
final class PageLayoutModeTests: XCTestCase {

    func testAllCasesOrderAndCount() {
        XCTAssertEqual(PageLayoutMode.allCases,
                       [.singlePage, .singleContinuous, .twoUp, .twoUpContinuous, .threeUp, .fourUp])
    }

    /// Raw values persist per-window via @SceneStorage — a rename silently
    /// resets every user's saved reading layout, so pin them.
    func testRawValuesAreStable() {
        XCTAssertEqual(PageLayoutMode.singlePage.rawValue, "Single Page")
        XCTAssertEqual(PageLayoutMode.singleContinuous.rawValue, "Single Page Continuous")
        XCTAssertEqual(PageLayoutMode.twoUp.rawValue, "Two Up")
        XCTAssertEqual(PageLayoutMode.twoUpContinuous.rawValue, "Two Up Continuous")
        XCTAssertEqual(PageLayoutMode.threeUp.rawValue, "Three Up")
        XCTAssertEqual(PageLayoutMode.fourUp.rawValue, "Four Up")
    }

    func testIdAndLabelMirrorRawValue() {
        for mode in PageLayoutMode.allCases {
            XCTAssertEqual(mode.id, mode.rawValue)
            XCTAssertEqual(mode.label, mode.rawValue)
        }
    }

    func testColumnCounts() {
        XCTAssertEqual(PageLayoutMode.singlePage.columns, 1)
        XCTAssertEqual(PageLayoutMode.singleContinuous.columns, 1)
        XCTAssertEqual(PageLayoutMode.twoUp.columns, 2)
        XCTAssertEqual(PageLayoutMode.twoUpContinuous.columns, 2)
        XCTAssertEqual(PageLayoutMode.threeUp.columns, 3)
        XCTAssertEqual(PageLayoutMode.fourUp.columns, 4)
    }

    func testContinuousFlag() {
        // Paged (one spread at a time).
        XCTAssertFalse(PageLayoutMode.singlePage.isContinuous)
        XCTAssertFalse(PageLayoutMode.twoUp.isContinuous)
        // Scrolling.
        XCTAssertTrue(PageLayoutMode.singleContinuous.isContinuous)
        XCTAssertTrue(PageLayoutMode.twoUpContinuous.isContinuous)
        XCTAssertTrue(PageLayoutMode.threeUp.isContinuous)
        XCTAssertTrue(PageLayoutMode.fourUp.isContinuous)
    }

    // MARK: - PDFKit-native vs custom-grid partition (the two-tier split)

    func testPdfDisplayModeMapsTierOneModes() {
        XCTAssertEqual(PageLayoutMode.singlePage.pdfDisplayMode, .singlePage)
        XCTAssertEqual(PageLayoutMode.singleContinuous.pdfDisplayMode, .singlePageContinuous)
        XCTAssertEqual(PageLayoutMode.twoUp.pdfDisplayMode, .twoUp)
        XCTAssertEqual(PageLayoutMode.twoUpContinuous.pdfDisplayMode, .twoUpContinuous)
    }

    /// 3-up / 4-up exceed PDFKit's two-up ceiling → nil ⇒ custom grid (Tier 2).
    func testTierTwoModesHaveNoPdfDisplayMode() {
        XCTAssertNil(PageLayoutMode.threeUp.pdfDisplayMode)
        XCTAssertNil(PageLayoutMode.fourUp.pdfDisplayMode)
    }

    func testIsPDFKitNativeMatchesDisplayModePresence() {
        for mode in PageLayoutMode.allCases {
            XCTAssertEqual(mode.isPDFKitNative, mode.pdfDisplayMode != nil, "\(mode)")
        }
        XCTAssertTrue(PageLayoutMode.twoUpContinuous.isPDFKitNative)
        XCTAssertFalse(PageLayoutMode.fourUp.isPDFKitNative)
    }

    func testSystemImagesAreNonEmptyAndDistinct() {
        let images = PageLayoutMode.allCases.map(\.systemImage)
        XCTAssertFalse(images.contains(""))
        XCTAssertEqual(Set(images).count, images.count, "each mode maps to a distinct SF Symbol")
    }
}
