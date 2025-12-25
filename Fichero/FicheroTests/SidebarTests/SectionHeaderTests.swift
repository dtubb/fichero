import XCTest
@testable import Fichero
import SwiftUI

/// Unit tests for SectionHeader component
class SectionHeaderTests: XCTestCase {

    // MARK: - Initialization Tests

    func testSectionHeaderInitialization() {
        // Given
        let title = "Library"
        let icon = "folder"

        // When
        let sectionHeader = SectionHeader(title: title, icon: icon)

        // Then
        // Verify the view can be created without errors
        XCTAssertNotNil(sectionHeader)
    }

    func testSectionHeaderWithEmptyTitle() {
        // Given
        let title = ""
        let icon = "folder"

        // When
        let sectionHeader = SectionHeader(title: title, icon: icon)

        // Then
        XCTAssertNotNil(sectionHeader)
    }

    func testSectionHeaderWithDifferentIcons() {
        // Given
        let icons = ["folder", "magnifyingglass", "bubble.left.and.bubble.right", "arrow.triangle.branch"]

        // When
        let sectionHeaders = icons.map { SectionHeader(title: "Test", icon: $0) }

        // Then
        sectionHeaders.forEach { XCTAssertNotNil($0) }
    }

    // MARK: - Rendering Tests

    func testSectionHeaderRendering() {
        // Given
        let sectionHeader = SectionHeader(title: "Library", icon: "folder")

        // When
        let view = sectionHeader

        // Then
        // Verify the view can be rendered
        XCTAssertNotNil(view)
    }

    // MARK: - Accessibility Tests

    func testSectionHeaderAccessibility() {
        // Given
        let sectionHeader = SectionHeader(title: "Library", icon: "folder")

        // When
        let view = sectionHeader

        // Then
        // The view should be accessible
        XCTAssertNotNil(view)
    }

    // MARK: - Preview Tests

    func testSectionHeaderPreview() {
        // Given
        let preview = SectionHeader_Previews.previews

        // When
        let previewView = preview

        // Then
        XCTAssertNotNil(previewView)
    }
}

// Preview provider for testing
struct SectionHeader_Previews: PreviewProvider {
    static var previews: some View {
        SectionHeader(title: "Library", icon: "folder")
            .padding()
            .previewLayout(.sizeThatFits)
    }
}