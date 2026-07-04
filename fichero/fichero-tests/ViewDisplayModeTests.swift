import XCTest

@testable import Fichero

/// Coverage for the Canvas & Space view-mode enum (#3081): the rename
/// `.map`→`.canvas`, the new `.space` case, and the legacy-rawValue migration
/// baked into `init?(rawValue:)`. This is the P1 foundation contract — the
/// enum must stay coherent and keep migrating old persisted values before any
/// renderer is wired.
final class ViewDisplayModeTests: XCTestCase {

    // MARK: - Legacy rawValue migration (the persistence seam)

    func testLegacyMapMigratesToCanvas() {
        XCTAssertEqual(ViewDisplayMode(rawValue: "Map"), .canvas)
    }

    func testLegacySpatialMigratesToCanvas() {
        // "Spatial (2D)" was merged into Canvas (#2667).
        XCTAssertEqual(ViewDisplayMode(rawValue: "Spatial"), .canvas)
    }

    func testLegacyRealityKitMigratesToSpace() {
        // The old 3D RealityKit / Mind Palace render is the new .space case.
        XCTAssertEqual(ViewDisplayMode(rawValue: "RealityKit"), .space)
    }

    func testMigratedValueRoundTripsToCanonicalRawValue() {
        // A migrated value must persist back as the canonical rawValue so the
        // legacy string is rewritten on next save, not carried forever.
        XCTAssertEqual(ViewDisplayMode(rawValue: "Map")?.rawValue, "Canvas")
        XCTAssertEqual(ViewDisplayMode(rawValue: "RealityKit")?.rawValue, "Space")
    }

    // MARK: - Canonical decode

    func testCanonicalRawValuesDecode() {
        XCTAssertEqual(ViewDisplayMode(rawValue: "Icon"), .icon)
        XCTAssertEqual(ViewDisplayMode(rawValue: "List"), .list)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Table"), .table)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Canvas"), .canvas)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Space"), .space)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Workspace"), .workspace)
    }

    func testUnknownRawValueIsNil() {
        XCTAssertNil(ViewDisplayMode(rawValue: "Nope"))
        XCTAssertNil(ViewDisplayMode(rawValue: ""))
    }

    // MARK: - Selectable set + labels

    func testSelectableCasesAreTheCoherentSet() {
        // icon/list/table/canvas/space — workspace is offered separately behind
        // its feature gate, so it is not in the base selectable set (#3081).
        XCTAssertEqual(ViewDisplayMode.selectableCases, [.icon, .list, .table, .canvas, .space])
        XCTAssertFalse(ViewDisplayMode.selectableCases.contains(.workspace))
    }

    func testAllCasesNoLongerIncludeRetiredAliases() {
        // The dead decode-only aliases are gone from the case list entirely.
        XCTAssertEqual(ViewDisplayMode.allCases, [.icon, .list, .table, .canvas, .space, .workspace])
    }

    func testLabels() {
        XCTAssertEqual(ViewDisplayMode.canvas.label, "Canvas")
        XCTAssertEqual(ViewDisplayMode.space.label, "Space")
        XCTAssertEqual(ViewDisplayMode.table.label, "Columns")
    }
}
