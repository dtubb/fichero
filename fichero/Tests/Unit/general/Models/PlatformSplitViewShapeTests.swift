@testable import Fichero
import XCTest

/// I1 item 5: the iOS `PlatformHSplitView` shim stacks at compact width, so an
/// iPhone never shows two ~195pt columns. Source-shape guard (no window server).
@MainActor
final class PlatformSplitViewShapeTests: XCTestCase {
    func testIOSHSplitShimStacksAtCompactWidth() throws {
        let source = try AppSource.text("Models/Platform/PlatformAliases.swift")
        let start = try XCTUnwrap(source.range(of: "struct PlatformHSplitView"))
        let end = try XCTUnwrap(source.range(of: "struct PlatformVSplitView", range: start.upperBound..<source.endIndex))
        let shim = String(source[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(shim.contains("horizontalSizeClass"), "the shim no longer reads the size class")
        XCTAssertTrue(shim.contains("VStack"), "compact width must stack the panes")
        XCTAssertTrue(shim.contains("HStack"), "regular width keeps side-by-side panes")
    }
}
