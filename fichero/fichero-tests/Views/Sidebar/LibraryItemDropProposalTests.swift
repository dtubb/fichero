import SwiftUI
import UniformTypeIdentifiers
import XCTest

@testable import Fichero

/// #4401 (reopened): *"it lets me drop, but it has a `+` icon on the cursor as
/// if I'm copying — I'm moving — and then nothing happens."*
///
/// Two defects in one gesture, with two separate causes:
///
///  1. **The cursor lies.** `.onDrop(of:isTargeted:perform:)` has no say over
///     the drag operation — SwiftUI always proposes `.copy`. Every in-app drop
///     surface used that spelling, so every MOVE was badged `+`. It was correct
///     once: the library folder cell was a Transferable `.dropDestination`,
///     which proposes `.move` for an in-app payload on its own, and widening it
///     to the untyped provider API (#4474/#4475, so a sidebar drag and a
///     library-pane drag reach ONE reader) silently traded the badge away. Only
///     `.onDrop(of:delegate:)` can answer, via `dropUpdated`.
///
///  2. **Nothing happens.** A `.onDrop(of: [.item])` on the whole
///     `NavigationSplitView` (`6a11a9fc2`) sat above every one of these
///     surfaces, claimed the drop, and then correctly refused it as internal —
///     so the drop was consumed and did nothing. That target is deleted;
///     `ContentPaneDropTargetTests` and `ExternalDropPromiseTypeTests` hold it
///     deleted.
///
/// The tests below are on the RULE and the WIRING. What they cannot prove is
/// delivery — #4473's standing point, and the reason this issue was closed
/// while failing. A live drag is still the acceptance step.
final class LibraryItemDropProposalTests: XCTestCase {

    private static func modifiers(option: Bool, command: Bool) -> SidebarDropModifiers {
        SidebarDropModifiers(option: option, command: command)
    }

    // MARK: - The rule

    /// The reported defect, stated: a plain intra-library drag is a MOVE and
    /// must not be badged as a copy.
    func testAPlainInAppDragProposesMoveNotCopy() {
        let proposed = libraryItemDropProposedOperation(
            isInAppDrag: true,
            modifiers: Self.modifiers(option: false, command: false)
        )
        XCTAssertEqual(proposed, .move)
        XCTAssertNotEqual(proposed, .copy, "the `+` badge is the bug (#4401)")
    }

    /// ⌥ genuinely copies, so `+` is right there. Without this the fix could be
    /// "always propose move", which lies in the other direction.
    func testOptionDragStillProposesCopy() {
        XCTAssertEqual(
            libraryItemDropProposedOperation(
                isInAppDrag: true,
                modifiers: Self.modifiers(option: true, command: false)
            ),
            .copy
        )
    }

    /// ⌘⌥ makes an alias. macOS has a badge for that; iOS does not, and the
    /// nearest truthful one there is copy — the destination does gain a row.
    func testCommandOptionDragProposesTheAliasBadgeWhereOneExists() {
        let proposed = libraryItemDropProposedOperation(
            isInAppDrag: true,
            modifiers: Self.modifiers(option: true, command: true)
        )
        #if os(macOS)
        XCTAssertEqual(proposed, .alias)
        #else
        XCTAssertEqual(proposed, .copy)
        #endif
        XCTAssertNotEqual(proposed, .move, "⌘⌥ leaves the original in place")
    }

    /// The control that keeps this from being "always move": an external file
    /// drop ingests bytes and leaves the original alone. That IS a copy, and
    /// badging it `.move` would tell a Finder user their file is about to be
    /// taken away.
    func testAnExternalFileDropStillProposesCopy() {
        for option in [true, false] {
            for command in [true, false] {
                XCTAssertEqual(
                    libraryItemDropProposedOperation(
                        isInAppDrag: false,
                        modifiers: Self.modifiers(option: option, command: command)
                    ),
                    .copy,
                    "external drops import a copy whatever is held (⌥\(option) ⌘\(command))"
                )
            }
        }
    }

    /// The badge and the outcome must be derived from ONE grammar. Two
    /// functions that happen to agree is the shape every bug in this family is
    /// made of, so this compares them across the whole modifier space rather
    /// than trusting the four cases above.
    func testTheProposedBadgeAgreesWithTheOperationTheDropWillPerform() {
        for option in [true, false] {
            for command in [true, false] {
                let mods = Self.modifiers(option: option, command: command)
                let performed = sidebarDropOperation(modifiers: mods, kind: .document)
                let proposed = libraryItemDropProposedOperation(isInAppDrag: true, modifiers: mods)
                switch performed {
                case .move:
                    XCTAssertEqual(proposed, .move, "⌥\(option) ⌘\(command)")
                case .copy:
                    XCTAssertEqual(proposed, .copy, "⌥\(option) ⌘\(command)")
                case .alias:
                    XCTAssertNotEqual(proposed, .move, "⌥\(option) ⌘\(command)")
                }
            }
        }
    }

    /// Non-document kinds have no ⌥/⌘⌥ grammar — they always move — so the
    /// badge must not offer one.
    func testNonDocumentKindsAlwaysMove() {
        for kind in [SidebarItemKind.savedSearch, .workflow, .conversation] {
            XCTAssertEqual(
                sidebarDropOperation(
                    modifiers: Self.modifiers(option: true, command: true), kind: kind
                ),
                .move,
                "\(kind) has no duplicate/alias endpoint"
            )
        }
    }

    // MARK: - The wiring
    //
    // A pure rule nothing calls protects nothing (`88629d0a8`'s own note). These
    // pin that every surface accepting an in-app item drag actually reaches the
    // delegate, because the closure form is what produced the wrong badge and
    // is one keystroke away at every one of them.

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// Every in-app drop surface takes the delegate. Listed explicitly rather
    /// than globbed: the point is that a NEW surface has to be added here, the
    /// way the library header was forgotten when the row was fixed (#4401).
    func testEveryInAppDropSurfaceUsesTheDelegateNotTheClosure() throws {
        let surfaces = [
            "Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift",
            "Views/Sidebar/Sections/SidebarSectionHeader.swift",
            "Views/Library/ViewModes/LibraryView+CellDrop.swift"
        ]
        for path in surfaces {
            let code = try Self.appSource(path)
                .split(separator: "\n", omittingEmptySubsequences: false)
                .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
                .joined(separator: "\n")
            XCTAssertTrue(
                code.contains("LibraryItemDropDelegate("),
                "\(path) must propose its operation, or a move is badged `+` (#4401)"
            )
            XCTAssertFalse(
                code.contains("isTargeted: $isDropTargeted) { providers in"),
                "\(path) is back on the closure form, which cannot propose `.move`"
            )
            XCTAssertFalse(
                code.contains("isTargeted: $isTargeted) { providers in"),
                "\(path) is back on the closure form, which cannot propose `.move`"
            )
        }
    }

    /// The delegate must hand the SAME type set to `itemProviders(for:)` that
    /// the surface declared. A narrower set collects fewer providers than the
    /// drop was accepted for — a drop that vanishes, which is the whole
    /// complaint.
    func testTheDelegateCollectsProvidersForTheTypesItAccepted() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/LibraryItemDropDelegate.swift")
        XCTAssertTrue(source.contains("info.itemProviders(for: acceptedTypes)"))
        XCTAssertTrue(
            source.contains("func validateDrop"),
            "validateDrop must be explicit — the default could refuse drops the closure accepted"
        )
    }

    /// `dropUpdated` is the one place the "sample modifiers once at the entry
    /// point" rule is exempted, because the badge must track the key being held
    /// right now. Stated here so the exemption stays deliberate.
    func testTheBadgeReReadsModifiersWhileTheDropIsStillHovering() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/LibraryItemDropDelegate.swift")
        let updated = try XCTUnwrap(
            source.range(of: "func dropUpdated").map { String(source[$0.lowerBound...]) }
        )
        XCTAssertTrue(updated.contains(".current()"))
    }

    /// The drop must clear its own hover wash — a row rebuilt mid-drag can lose
    /// the trailing `dropExited` and strand the accent on, which reads as a
    /// stuck selection (#4229). `handleRowDrop` already did this; moving to a
    /// delegate must not lose it.
    func testPerformingTheDropClearsTheHoverHighlight() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/LibraryItemDropDelegate.swift")
        let perform = try XCTUnwrap(
            source.range(of: "func performDrop").map { String(source[$0.lowerBound...]) }
        )
        XCTAssertTrue(perform.contains("isTargeted.wrappedValue = false"))
    }
}
