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

    func testAdaptivePresentationUsesNavigationPushForCompactWidth() {
        XCTAssertEqual(
            InspectorPlacement.adaptivePresentation(horizontalSizeClass: .compact),
            .navigationPush
        )
    }

    func testAdaptivePresentationUsesDockedInspectorForRegularWidth() {
        XCTAssertEqual(
            InspectorPlacement.adaptivePresentation(horizontalSizeClass: .regular),
            .docked
        )
    }

    func testAdaptivePresentationKeepsDockedInspectorForExplicitDockedPlacement() {
        XCTAssertEqual(
            InspectorPlacement.adaptivePresentation(horizontalSizeClass: .compact, requested: .docked),
            .docked
        )
    }

    func testAdaptivePresentationHonorsExplicitSheetPlacement() {
        XCTAssertEqual(
            InspectorPlacement.adaptivePresentation(horizontalSizeClass: .regular, requested: .sheet),
            .sheet
        )
    }
}
