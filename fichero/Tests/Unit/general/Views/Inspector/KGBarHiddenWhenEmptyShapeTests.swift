@testable import Fichero
import XCTest

/// #5508: the KG tab shows no "0 entities / Prune trivial" bar when there is nothing in it, but keeps
/// the bar while a kind filter is active (the filter menu lives there). Source-shape guard.
@MainActor
final class KGBarHiddenWhenEmptyShapeTests: XCTestCase {
    func testMiniToolbarIsHiddenOnlyWhenEmptyAndUnfiltered() throws {
        let source = try AppSource.code("Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift")
        let gate = try XCTUnwrap(source.range(of: "if !(grouped.isEmpty && hiddenKindsCSV.isEmpty) {"))
        let tail = String(source[gate.upperBound...].prefix(120))
        XCTAssertTrue(tail.contains("kgMiniToolbar"), "the bar is no longer behind the empty-and-unfiltered gate")
    }
}
