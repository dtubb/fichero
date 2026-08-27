@testable import Fichero
import SwiftUI
import XCTest

/// Tests for two untested display/theme value enums: ViewMode (raw values +
/// displayName + systemImage) and SpaceTheme's SwiftUI colour delegation. Pure
/// presentation logic, no engine. (SpaceTheme's platform/material colour
/// variants are thin alpha wrappers over the same switch and are excluded to
/// avoid brittle catalog-colour equality.)
final class ViewModeAndSpaceThemeTests: XCTestCase {

    // MARK: - ViewMode

    private let allModes: [ViewMode] = [
        .library, .workflow, .chat, .search, .batches,
        .automation, .running, .history, .issues
    ]

    func testViewModeRawValuesRoundTrip() throws {
        for mode in allModes {
            let data = try JSONEncoder().encode(mode)
            let decoded = try JSONDecoder().decode(ViewMode.self, from: data)
            XCTAssertEqual(decoded, mode)
        }
        // A couple of concrete raws (the wire form is the lowercase case name).
        XCTAssertEqual(ViewMode.library.rawValue, "library")
        XCTAssertEqual(ViewMode.automation.rawValue, "automation")
    }

    func testViewModeDisplayNamesAreCapitalizedAndComplete() {
        XCTAssertEqual(ViewMode.library.displayName, "Library")
        XCTAssertEqual(ViewMode.workflow.displayName, "Workflow")
        XCTAssertEqual(ViewMode.batches.displayName, "Batches")
        XCTAssertEqual(ViewMode.issues.displayName, "Issues")
        // Every mode has a non-empty display name.
        for mode in allModes {
            XCTAssertFalse(mode.displayName.isEmpty, "\(mode)")
        }
    }

    func testViewModeSystemImagesAreDistinctAndNonEmpty() {
        let images = allModes.map(\.systemImage)
        XCTAssertFalse(images.contains(""))
        // Each mode maps to a distinct SF Symbol.
        XCTAssertEqual(Set(images).count, images.count)
        XCTAssertEqual(ViewMode.search.systemImage, "magnifyingglass")
        XCTAssertEqual(ViewMode.history.systemImage, "clock")
    }

    // MARK: - SpaceTheme colour delegation

    func testSpaceThemeNodeColourDelegatesToNodeType() {
        for nodeType in SpatialNodeType.allCases {
            XCTAssertEqual(SpaceTheme.swiftUIColor(for: nodeType), nodeType.color, "\(nodeType)")
        }
    }

    func testSpaceThemeLinkColourDelegatesToLinkType() {
        for linkType in LinkType.allCases {
            XCTAssertEqual(SpaceTheme.swiftUIColor(for: linkType), linkType.color, "\(linkType)")
        }
    }
}
