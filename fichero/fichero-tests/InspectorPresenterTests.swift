@testable import Fichero
import SwiftUI
import XCTest

final class InspectorPresenterTests: XCTestCase {
    func testAdaptiveDefaultUsesSheetForCompactWidth() {
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: .compact),
            .sheet
        )
    }

    func testAdaptiveDefaultUsesDockedInspectorForRegularWidth() {
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: .regular),
            .docked
        )
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: nil),
            .docked
        )
    }

    func testAdaptiveDefaultHonorsRequestedPlacement() {
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: .compact, requested: .floating),
            .floating
        )
    }
}
