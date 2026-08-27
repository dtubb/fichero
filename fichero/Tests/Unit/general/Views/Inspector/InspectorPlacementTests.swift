@testable import Fichero
import SwiftUI
import XCTest

/// Completes the `InspectorPlacement.adaptiveDefault` matrix (#3017): an explicit
/// user `requested` placement always wins; otherwise compact width defaults to a
/// sheet and everything else (regular / unknown) to the docked column.
final class InspectorPlacementTests: XCTestCase {
    func testCompactDefaultsToSheet() {
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: .compact),
            .sheet
        )
    }

    func testRegularDefaultsToDocked() {
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: .regular),
            .docked
        )
    }

    func testUnknownSizeClassDefaultsToDocked() {
        XCTAssertEqual(
            InspectorPlacement.adaptiveDefault(horizontalSizeClass: nil),
            .docked
        )
    }

    /// An explicit request overrides the size-class default for every placement
    /// and every size class.
    func testRequestedPlacementAlwaysWins() {
        let sizeClasses: [UserInterfaceSizeClass?] = [.compact, .regular, nil]
        for requested in InspectorPlacement.allCases {
            for sizeClass in sizeClasses {
                XCTAssertEqual(
                    InspectorPlacement.adaptiveDefault(horizontalSizeClass: sizeClass, requested: requested),
                    requested,
                    "requested \(requested) sizeClass \(String(describing: sizeClass))"
                )
            }
        }
    }
}
