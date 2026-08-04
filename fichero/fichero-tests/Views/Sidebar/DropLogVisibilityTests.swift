@testable import Fichero
import XCTest

/// #4533 — Daniel: "lots of sidebar drops aren't logged either."
///
/// The shared `DragDropLog` seam already existed and its SHAPE was right —
/// surface, `drop#N` session stamp, a reason on every refusal. The defect was
/// the LEVEL. Every non-refusal line was `.info`, and macOS does not persist
/// `.info` or `.debug`; they live in a memory ring buffer. Measured on the live
/// build, `log show --info --debug --predicate 'category == "dragdrop"'`
/// returned zero rows over a window that contained real drops.
///
/// So only refusals survived a session. That makes "refused" and "never
/// arrived" indistinguishable after the fact — and those have opposite fixes,
/// which is precisely why drop reports kept costing a diagnosis round.
///
/// Outcomes are now `.notice` (the default level, persisted). These guards are
/// source-shape because a log LEVEL is not observable from a unit test — there
/// is no API to ask OSLog what a call site emitted — but it is exactly the
/// property that regressed, so it is the property to pin.
final class DropLogVisibilityTests: XCTestCase {

    /// #4493: routed through the shared `AppSource` walk instead of
    /// counting `deletingLastPathComponent()` calls. Counting is correct
    /// only for this file's CURRENT depth — move the file and it resolves
    /// somewhere else and fails later as an unrelated file-not-found.
    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    private static func dragDropLogBody() throws -> String {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarDropProviderReader.swift")
        let start = try XCTUnwrap(source.range(of: "enum DragDropLog {"))
        let end = try XCTUnwrap(
            source.range(of: "// MARK: - Reading an in-app drop's payload", range: start.upperBound..<source.endIndex)
        )
        return String(source[start.upperBound..<end.lowerBound])
    }

    /// The regression: nothing in the seam may emit at a level macOS discards.
    func testNoDropLogLineIsEmittedAtANonPersistedLevel() throws {
        let body = try Self.dragDropLogBody()

        XCTAssertFalse(
            body.contains("logger.info("),
            """
            DragDropLog emits at .info again (#4533). macOS does not persist \
            .info, so those lines cannot be read back from a session that has \
            already happened — which is the only time a drop report is \
            diagnosed. Use .notice for outcomes.
            """
        )
        XCTAssertFalse(
            body.contains("logger.debug("),
            "DragDropLog emits at .debug — not persisted, same defect as .info (#4533)"
        )
    }

    /// Both halves must survive, not just the refusals: without the accepted
    /// path in the same stream you cannot tell a refusal from a drop that never
    /// reached the surface at all.
    func testBothOutcomesAndRefusalsArePersistedLevels() throws {
        let body = try Self.dragDropLogBody()

        XCTAssertTrue(body.contains("logger.notice("), "outcomes must persist (.notice)")
        XCTAssertTrue(body.contains("logger.error("), "refusals must stay loud (.error)")
    }

    /// The session stamp is what proves a multi-surface trail is ONE drop.
    /// Losing it would make the now-visible lines ambiguous instead of useful.
    func testEveryLineStillCarriesTheDropSessionStamp() throws {
        let body = try Self.dragDropLogBody()
        let logCalls = body.components(separatedBy: "logger.").dropFirst()

        XCTAssertFalse(logCalls.isEmpty, "no log calls found — this guard measures nothing")
        for call in logCalls {
            let line = call.prefix(400)
            XCTAssertTrue(
                line.contains("dropTag"),
                "a DragDropLog line omits the drop#N stamp, so its trail can't be tied to one drop (#4533)"
            )
        }
    }

    /// The three refusal paths that used to be bare `return false`. Each is a
    /// way a drop can visibly do nothing, and each was silent.
    func testPreviouslySilentRowRefusalsNowReportAReason() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift")

        XCTAssertFalse(
            source.contains("guard !providers.isEmpty else { return false }"),
            "the empty-providers refusal is silent again (#4533)"
        )
        XCTAssertFalse(
            source.contains("guard mightBeInternal || capabilityRoute == .externalFiles else { return false }"),
            "the unroutable-payload refusal is silent again — the commonest silent drop (#4533)"
        )
        XCTAssertFalse(
            source.contains("guard operation != .move, let library else { return false }"),
            "the insertion refusal is silent again (#4533)"
        )
        XCTAssertEqual(
            source.components(separatedBy: "DragDropLog.refused(").count - 1, 4,
            "expected every wired refusal in this file to report through the shared seam"
        )
    }

    /// The whole drop trail must sit in ONE category, or the drop#N stamp has
    /// nothing to correlate across surfaces — which is what made a single
    /// header drop read as two performs. `LibraryHeaderDrop` was a private
    /// third category doing exactly that.
    func testNoDropPathDeclaresItsOwnLoggerCategory() throws {
        for path in [
            "Views/Sidebar/Sections/SidebarSectionHeader.swift",
            "Views/Sidebar/Sections/SidebarView+LibraryHeaderHelpers.swift",
            "Views/Sidebar/ItemRow/SidebarDropOperation.swift"
        ] {
            let source = try Self.appSource(path)
            XCTAssertFalse(
                source.contains("LibraryHeaderDrop"),
                "\(path) resurrected the private LibraryHeaderDrop category (#4533)"
            )
        }
    }

    /// The literal shape of "the drop did nothing and the log is empty": a
    /// classified payload falling into `.unsupported` and hitting `break`.
    func testUnsupportedPayloadOnTheHeaderIsReported() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        let start = try XCTUnwrap(source.range(of: "case .unsupported:"))
        let branch = String(source[start.lowerBound..<source.index(start.lowerBound, offsetBy: 400)])

        XCTAssertTrue(
            branch.contains("DragDropLog.refused("),
            "an UNSUPPORTED payload on the library header goes unreported again (#4533)"
        )
    }

    /// Every surface that can swallow a drop reports through the seam. Counted,
    /// not just present: a file can lose one refusal and still contain others.
    func testEverySidebarDropSurfaceReportsRefusals() throws {
        let expected = [
            "Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift": 4,
            "Views/Sidebar/ItemRow/SidebarDropOperation.swift": 2,
            "Views/Sidebar/Sections/SidebarView+LibraryHeaderHelpers.swift": 3,
            "Views/Sidebar/Sections/SidebarSectionHeader.swift": 7
        ]
        for (path, count) in expected {
            let source = try Self.appSource(path)
            XCTAssertEqual(
                source.components(separatedBy: "DragDropLog.refused(").count - 1, count,
                "\(path) lost a refusal report (#4533)"
            )
        }
    }

    /// Side effect that must NOT happen: a second logging seam. The codebase
    /// already learned this with classifiers — a copied one is how the section
    /// header grew a divergent routing rule (#4401). Refusals go through
    /// `DragDropLog` so none of them can forget the reason.
    func testRefusalsGoThroughTheOneSharedSeam() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift")

        XCTAssertFalse(
            source.contains("Logger(subsystem:"),
            "SidebarItemRow+Drop declares its own Logger — use the shared DragDropLog seam (#4533)"
        )
    }
}
