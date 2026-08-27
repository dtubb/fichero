@testable import Fichero
import SwiftUI
import XCTest

/// #4096 — sidebar row insets had no single source of truth.
///
/// Three call sites each held their own `EdgeInsets` literal. The audit is on
/// the issue; the short version is that the divergence was NOT uniform drift:
///
/// - leading (8 / 12 / 16) encodes real nesting depth in a 4pt step,
/// - trailing already agreed at 8 everywhere,
/// - vertical genuinely disagrees, and is preserved here rather than
///   harmonised so this refactor renders identically to what shipped.
///
/// These tests do two different jobs, and the second is the one that makes the
/// consolidation stick: pinning the numbers proves nothing moved, but only the
/// source assertion stops the next row site from writing its own literal —
/// which is how three of them appeared.
final class SidebarRowMetricsTests: XCTestCase {

    // MARK: - Nothing moved

    func testInsetsMatchWhatEachCallSiteUsedBefore() {
        XCTAssertEqual(SidebarRowMetrics.insets(.library), EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
        XCTAssertEqual(
            SidebarRowMetrics.insets(.libraryItem),
            EdgeInsets(top: 0, leading: 12, bottom: 0, trailing: 8)
        )
        XCTAssertEqual(
            SidebarRowMetrics.insets(.inlineNotice),
            EdgeInsets(top: 2, leading: 16, bottom: 2, trailing: 8)
        )
    }

    // MARK: - The structure the leading values encode

    func testLeadingStepsByTheIndentUnitPerDepth() {
        // If a later edit "tidies" these to one value the sidebar loses the
        // structure that distinguishes a library from a row inside it.
        let library = SidebarRowMetrics.leading(.library)
        let item = SidebarRowMetrics.leading(.libraryItem)
        let notice = SidebarRowMetrics.leading(.inlineNotice)

        XCTAssertEqual(item - library, 4, "one indent unit per level")
        XCTAssertEqual(notice - item, 4, "and the step is uniform")
    }

    func testTrailingIsTheSameAtEveryDepth() {
        // Unanimous before consolidation; a right edge that varies by depth
        // would read as ragged rather than nested.
        for depth in [SidebarRowMetrics.Depth.library, .libraryItem, .inlineNotice] {
            XCTAssertEqual(SidebarRowMetrics.insets(depth).trailing, SidebarRowMetrics.trailing)
        }
    }

    // MARK: - The disagreement, recorded rather than hidden

    func testVerticalStillDisagreesAndThatIsDeliberateForNow() {
        // Documented in #4476. Pinned so the day someone harmonises it, this
        // test fails and forces the change to be a DECISION with eyes on it,
        // rather than a side effect of unrelated work.
        XCTAssertEqual(SidebarRowMetrics.vertical(.libraryItem), 0)
        XCTAssertEqual(SidebarRowMetrics.vertical(.library), 2)
        XCTAssertEqual(SidebarRowMetrics.vertical(.inlineNotice), 2)
    }

    // MARK: - The part that makes it stick

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// Sweeps the sidebar rather than the three files that happened to be wrong
    /// (#4447's lesson): a fourth row site with its own literal is the same bug,
    /// and naming only the known three would not see it.
    func testNoSidebarRowWritesItsOwnInsetLiteral() throws {
        let sidebar = try AppSource.root().appendingPathComponent("Views/Sidebar")

        let files = try FileManager.default
            .subpathsOfDirectory(atPath: sidebar.path)
            .filter { $0.hasSuffix(".swift") }

        XCTAssertFalse(files.isEmpty, "found no Swift under Views/Sidebar — the sweep went blind")

        var offenders: [String] = []
        for relative in files {
            let source = try String(contentsOf: sidebar.appendingPathComponent(relative), encoding: .utf8)
            let code = source
                .split(separator: "\n", omittingEmptySubsequences: false)
                .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
                .joined(separator: "\n")
            if code.contains("listRowInsets(EdgeInsets") {
                offenders.append(relative)
            }
        }

        XCTAssertTrue(
            offenders.isEmpty,
            "these sidebar rows bypass SidebarRowMetrics and invent their own insets (#4096): \(offenders)"
        )
    }

    /// The sweep above passes trivially if every call site stopped setting
    /// insets at all, so assert the metrics ARE being used.
    func testTheThreeKnownRowSitesActuallyUseTheMetrics() throws {
        let cases = [
            ("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift", "SidebarRowMetrics.insets(.library)"),
            ("Views/Sidebar/Sections/SidebarView+UnifiedRows.swift", "SidebarRowMetrics.insets(.libraryItem)"),
            ("Views/Sidebar/Sections/SidebarView+PinnedNavigationRows.swift", "SidebarRowMetrics.insets(.inlineNotice)")
        ]
        for (path, expected) in cases {
            XCTAssertTrue(try Self.appSource(path).contains(expected), "\(path) must read its insets from the metrics")
        }
    }
}
