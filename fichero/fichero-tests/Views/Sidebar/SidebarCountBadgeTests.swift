@testable import Fichero
import XCTest

/// #4095 — sidebar counts are drawn by the system, not by hand.
///
/// The library header rendered its count as
/// `if itemCount > 0 { Text("\(itemCount)").font(.caption).foregroundStyle(.secondary) }`
/// — a manual hide-at-zero, a manual font and a manual colour, each of them
/// re-deciding something the platform already decides for a sidebar count.
///
/// `.badge(Int)` hides itself at zero and carries the treatment NetNewsWire
/// switched to by hand under `#available(macOS 26, *)`. Adopting it is not a
/// guess about appearance; hand-drawing it was.
final class SidebarCountBadgeTests: XCTestCase {

    private static let sidebar = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Sidebar
        .deletingLastPathComponent()   // Views
        .deletingLastPathComponent()   // fichero-tests
        .deletingLastPathComponent()   // fichero
        .appendingPathComponent("fichero/Views/Sidebar")

    private static func sidebarSwiftFiles() throws -> [String] {
        try FileManager.default
            .subpathsOfDirectory(atPath: sidebar.path)
            .filter { $0.hasSuffix(".swift") }
    }

    private static func code(_ relative: String) throws -> String {
        let source = try String(contentsOf: sidebar.appendingPathComponent(relative), encoding: .utf8)
        return source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    func testTheLibraryHeaderUsesTheNativeBadge() throws {
        let header = try Self.code("Sections/SidebarSectionHeader.swift")

        XCTAssertTrue(header.contains(".badge(itemCount)"))
    }

    /// The hand-drawn chrome must be GONE, not merely unused. Leaving it in
    /// place beside the badge is how a surface ends up rendering a count twice
    /// the first time someone edits the wrong one.
    ///
    /// Scoped to `headerContent`, NOT the whole file. My first draft banned
    /// `if itemCount > 0` file-wide and failed on correct code: the
    /// accessibility label has its own zero-guard, and that one is right —
    /// an empty library should be announced without a count phrase, which is a
    /// sentence-construction concern, not view chrome. A guard that cannot tell
    /// those apart would have forced someone to delete working code to get
    /// green.
    func testTheHandDrawnCountChromeIsRemoved() throws {
        let header = try Self.code("Sections/SidebarSectionHeader.swift")
        let body = try XCTUnwrap(header.range(of: "private var headerContent: some View"))
        let end = header.range(of: "private var locationBadge", range: body.upperBound..<header.endIndex)
        let block = String(header[body.upperBound..<(end?.lowerBound ?? header.endIndex)])

        XCTAssertFalse(block.contains("Text(\"\\(itemCount)\")"))
        XCTAssertFalse(
            block.contains("if itemCount > 0"),
            "`.badge(Int)` hides itself at zero — a manual guard here means someone doubted it"
        )
    }

    /// Sweeps the whole sidebar, not the one file that happened to be wrong
    /// (#4447's lesson). A second surface hand-drawing a count is the same
    /// defect, and naming only the known site would not see it.
    func testNoSidebarSurfaceHandDrawsACount() throws {
        let files = try Self.sidebarSwiftFiles()
        XCTAssertFalse(files.isEmpty, "found no Swift under Views/Sidebar — the sweep went blind")

        var offenders: [String] = []
        for relative in files where try Self.code(relative).contains("Text(\"\\(itemCount)\")") {
            offenders.append(relative)
        }

        XCTAssertTrue(
            offenders.isEmpty,
            "these sidebar surfaces hand-draw a count instead of using .badge() (#4095): \(offenders)"
        )
    }

    /// The sweep above passes trivially if the sidebar simply stopped showing
    /// counts, so assert a badge is actually rendered somewhere.
    func testTheSidebarStillShowsACountSomewhere() throws {
        let files = try Self.sidebarSwiftFiles()
        let badged = try files.filter { try Self.code($0).contains(".badge(") }

        XCTAssertFalse(
            badged.isEmpty,
            "no sidebar surface renders a count at all — removing the chrome is not the same as adopting the badge"
        )
    }

    /// The VoiceOver label already spells the count out ("Global, library, 42
    /// documents") and is applied at the row's outer boundary, which replaces
    /// the composed children's labels rather than appending to them. Pinned
    /// because if that label is ever removed, the badge becomes the only
    /// announcement and the phrasing changes silently.
    func testTheAccessibilityLabelStillCarriesTheCountItself() throws {
        let header = try Self.code("Sections/SidebarSectionHeader.swift")

        XCTAssertTrue(header.contains(".accessibilityLabel(accessibilityLabel)"))
        XCTAssertTrue(header.contains("documents"), "the spoken label states the count in words")
    }
}
