@testable import Fichero
import Foundation
import XCTest

/// #4297 — clicking a page row sometimes DESELECTED it.
///
/// The click triggers the lazy child load; the `childrenCache` write rebuilds
/// the tree, and while the clicked row is momentarily absent from the rendered
/// rows `List(selection:)` writes the selection back WITHOUT it — erasing the
/// user's click. `sidebarResilientSelection` is the sanitizer the binding
/// setter now runs: a DROPPED destination whose row cannot currently be
/// resolved is kept (the rebuild is talking, not the user); drops of
/// resolvable rows — real deselects — pass through untouched.
@MainActor
final class SidebarSelectionResilienceTests: XCTestCase {

    private let pageRow = SidebarDestination.document("page-1")
    private let folderRow = SidebarDestination.document("folder-1")

    // MARK: - The regression: rebuild-time clear is ignored

    func testClearOfMomentarilyMissingRowIsIgnored() {
        // Reload in flight: the clicked row resolves to nothing right now.
        let result = SidebarView.sidebarResilientSelection(
            current: [pageRow],
            proposed: [],
            isMomentarilyMissing: { _ in true }
        )
        XCTAssertEqual(result, [pageRow], "the rebuild's clear must not erase the click")
    }

    func testPartialDropKeepsOnlyTheMissingRow() {
        // A rebuild drops the page row while the user's same gesture keeps the
        // folder selected — only the unresolvable row is restored.
        let result = SidebarView.sidebarResilientSelection(
            current: [pageRow, folderRow],
            proposed: [folderRow],
            isMomentarilyMissing: { $0 == pageRow }
        )
        XCTAssertEqual(result, [pageRow, folderRow])
    }

    // MARK: - Genuine user actions pass through

    func testDeselectOfResolvableRowIsHonored() {
        // Cmd-click deselect of a row that is right there: a real user action.
        let result = SidebarView.sidebarResilientSelection(
            current: [pageRow],
            proposed: [],
            isMomentarilyMissing: { _ in false }
        )
        XCTAssertTrue(result.isEmpty, "a deselect of a visible row must go through")
    }

    func testNewSelectionPassesThroughUnchanged() {
        let result = SidebarView.sidebarResilientSelection(
            current: [pageRow],
            proposed: [folderRow],
            isMomentarilyMissing: { _ in false }
        )
        XCTAssertEqual(result, [folderRow], "clicking another row replaces the selection")
    }

    func testAdditionsNeverConsultTheResolver() {
        // Pure addition (shift-extend): nothing dropped, resolver must not run
        // — a grow-only write can never be a rebuild artifact.
        var consulted = false
        let result = SidebarView.sidebarResilientSelection(
            current: [pageRow],
            proposed: [pageRow, folderRow],
            isMomentarilyMissing: { _ in
                consulted = true
                return true
            }
        )
        XCTAssertEqual(result, [pageRow, folderRow])
        XCTAssertFalse(consulted)
    }

    func testReplacementClickWinsOutrightEvenMidRebuild() {
        // The user clicks a NEW row while the old one is mid-rebuild: any
        // write that ADDS a row is a genuine gesture (List reconciliation only
        // removes), so the replacement is honored fully — no phantom multi-
        // selection.
        let result = SidebarView.sidebarResilientSelection(
            current: [pageRow],
            proposed: [folderRow],
            isMomentarilyMissing: { $0 == pageRow }
        )
        XCTAssertEqual(result, [folderRow])
    }

    func testEmptyToEmptyIsStable() {
        let result = SidebarView.sidebarResilientSelection(
            current: [],
            proposed: [],
            isMomentarilyMissing: { _ in true }
        )
        XCTAssertTrue(result.isEmpty)
    }

    // MARK: - delete.selection-safe (spec: sidebar-crud) — a deleted row must
    // NOT be resurrected. Root cause of "deleting a child lands you on the
    // parent": the resurrection filter could not tell a just-deleted row (gone)
    // from a mid-rebuild gap (coming back), so it kept the deleted row and the
    // selection then routed to its parent. `droppedRowIsMomentarilyMissing`
    // makes that distinction, driven by DocumentStore.recentlyDeletedDocumentIds.

    /// delete.selection-safe: a dropped row whose cache entry vanished because it
    /// was just DELETED is gone, not rebuilding — it must fall out of the
    /// selection, never be resurrected.
    func testRecentlyDeletedRowIsNotResurrected() {
        XCTAssertFalse(
            SidebarView.droppedRowIsMomentarilyMissing(
                pageRow, cachedItemMissing: true, wasRecentlyDeleted: true
            ),
            "a just-deleted row must not be treated as a momentary rebuild gap"
        )
    }

    /// The #4297 behavior the fix must preserve: a row missing due to a REBUILD
    /// (not deleted) is still momentarily missing and kept.
    func testRebuildGapRowIsStillKept() {
        XCTAssertTrue(
            SidebarView.droppedRowIsMomentarilyMissing(
                pageRow, cachedItemMissing: true, wasRecentlyDeleted: false
            ),
            "a rebuild-time gap must still be resilient (#4297)"
        )
    }

    /// A resolvable row (cache hit) is never momentarily missing, deleted or not.
    func testResolvableRowIsNeverMomentarilyMissing() {
        XCTAssertFalse(
            SidebarView.droppedRowIsMomentarilyMissing(
                pageRow, cachedItemMissing: false, wasRecentlyDeleted: false
            )
        )
    }

    /// Pinned/static rows (library, browser, run, KG collection) are never
    /// resolved through the cache, so a drop of one is always the user — never
    /// "momentarily missing", regardless of the cache/delete flags.
    func testPinnedRowIsNeverMomentarilyMissing() {
        XCTAssertFalse(
            SidebarView.droppedRowIsMomentarilyMissing(
                .library(UUID()), cachedItemMissing: true, wasRecentlyDeleted: false
            )
        )
    }
}
