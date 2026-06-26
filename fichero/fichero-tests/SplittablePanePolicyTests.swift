@testable import Fichero
import SwiftUI
import XCTest

final class SplittablePanePolicyTests: XCTestCase {
    func testShouldUseSplittablePaneTreatsCompactAsUnsupportedOnNonMac() {
        #if os(macOS)
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: nil))
        XCTAssertFalse(ContentView.shouldUseSplittablePane(horizontalSizeClass: .compact))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .regular))
        #else
        XCTAssertFalse(ContentView.shouldUseSplittablePane(horizontalSizeClass: .compact))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .regular))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: nil))
        #endif
    }

    func testShouldUseSplittablePaneCollapsesWhenWindowIsTooNarrow() {
        XCTAssertFalse(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular,
                windowWidth: 599,
                minimumWidth: 600
            )
        )
        XCTAssertTrue(
            ContentView.shouldUseSplittablePane(
                horizontalSizeClass: .regular,
                windowWidth: 601,
                minimumWidth: 600
            )
        )
    }
}
