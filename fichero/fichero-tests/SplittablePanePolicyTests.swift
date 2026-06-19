@testable import Fichero
import SwiftUI
import XCTest

final class SplittablePanePolicyTests: XCTestCase {
    func testShouldUseSplittablePaneTreatsCompactAsUnsupportedOnNonMac() {
        #if os(macOS)
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: nil))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .compact))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .regular))
        #else
        XCTAssertFalse(ContentView.shouldUseSplittablePane(horizontalSizeClass: .compact))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: .regular))
        XCTAssertTrue(ContentView.shouldUseSplittablePane(horizontalSizeClass: nil))
        #endif
    }
}
