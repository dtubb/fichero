import SwiftUI
import XCTest

@testable import Fichero

/// Tests for the shared adaptive mini-toolbar row (#3056, parent #2670):
/// the pure tier-policy math, component instantiability, and a source-surface
/// assertion that the regular-width fallback candidate uses the overflow menu.
final class MiniToolbarOverflowTests: XCTestCase {

    // MARK: - Tier policy (the per-platform button budget)

    func testCompactInlinesEssentialOnly() {
        XCTAssertEqual(MiniToolbarTierPolicy.inlineTiers(isCompact: true), [.essential])
    }

    func testRegularInlinesBothTiers() {
        XCTAssertEqual(
            MiniToolbarTierPolicy.inlineTiers(isCompact: false),
            [.essential, .secondary]
        )
    }

    func testSecondaryTierIsInlineOnlyOnRegular() {
        XCTAssertFalse(MiniToolbarTierPolicy.inlineTiers(isCompact: true).contains(.secondary))
        XCTAssertTrue(MiniToolbarTierPolicy.inlineTiers(isCompact: false).contains(.secondary))
    }

    func testEssentialTierAlwaysInline() {
        XCTAssertTrue(MiniToolbarTierPolicy.inlineTiers(isCompact: true).contains(.essential))
        XCTAssertTrue(MiniToolbarTierPolicy.inlineTiers(isCompact: false).contains(.essential))
    }

    // MARK: - Component instantiability

    func testRowIsInstantiable() {
        let row = AdaptiveMiniToolbarRow {
            Button("Primary") {}
        } secondary: {
            Button("Extra") {}
        } overflowMenu: {
            Button("Extra") {}
        }
        // Constructing the generic view proves the essential/secondary/overflow
        // ViewBuilder wiring compiles; the type name confirms it resolved.
        XCTAssertTrue(String(describing: type(of: row)).hasPrefix("AdaptiveMiniToolbarRow"))
    }

    // MARK: - Source-surface assertion (mirror WorkflowImportExportSurfaceTests)

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testRegularFallbackCandidateUsesOverflowMenu() throws {
        let source = try Self.appSource("Views/Components/MiniToolbarOverflow.swift")

        // Regular width fits-or-overflows via ViewThatFits, with the overflow
        // Menu (ellipsis.circle) as the fallback candidate — never a bar that
        // extends past the pane.
        XCTAssertTrue(source.contains("ViewThatFits(in: .horizontal)"))
        XCTAssertTrue(source.contains("ellipsis.circle"))
        XCTAssertTrue(source.contains("overflowMenuButton"))
        // The tiering is derived from the pure policy, not hand-rolled in body.
        XCTAssertTrue(source.contains("MiniToolbarTierPolicy.inlineTiers"))
    }

    func testReaderToolbarUsesSharedAdaptiveMiniToolbarRow() throws {
        let source = try Self.appSource("Views/Reader/ReaderToolbar.swift")

        XCTAssertTrue(source.contains("private var adaptiveToolsRow: some View"))
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("secondaryToolsCluster"))
        XCTAssertTrue(source.contains("overflowMenu"))
    }

    func testWorkflowToolbarUsesSharedAdaptiveMiniToolbarRow() throws {
        let source = try Self.appSource("Views/Workflow/WorkflowToolbar.swift")

        XCTAssertTrue(source.contains("private var adaptiveActionRow: some View"))
        XCTAssertTrue(source.contains("AdaptiveMiniToolbarRow {"))
        XCTAssertTrue(source.contains("trailing: {"))
        XCTAssertTrue(source.contains("runButton"))
    }
}
