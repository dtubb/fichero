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

    /// #6588: a raw `VSplitView` / `HSplitView` is macOS-only, so one in a view breaks the iOS build (batch-21's
    /// Activity pane did, 2026-11-16). Every view splits through `PlatformVSplitView` / `PlatformHSplitView`.
    func testNoViewUsesARawSplitView() throws {
        let files = try AppSource.swiftFiles(under: "Views")
        XCTAssertGreaterThan(files.count, 100, "the walk scanned too little to mean anything")
        let raw = try NSRegularExpression(pattern: #"(?<![A-Za-z])[HV]SplitView\s*[{(]"#)
        let offenders = files.filter { file in
            raw.firstMatch(in: file.code, range: NSRange(file.code.startIndex..., in: file.code)) != nil
        }.map(\.path)
        XCTAssertEqual(offenders, [], "use PlatformVSplitView / PlatformHSplitView; the raw ones do not exist on iOS")
    }
}
