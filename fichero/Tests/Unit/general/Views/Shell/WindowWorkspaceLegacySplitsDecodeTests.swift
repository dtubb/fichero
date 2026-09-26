@testable import Fichero
import Foundation
import Testing

/// source-model panes recon, slice F (2026-09-20): `PaneSplitCoordinator` and its
/// notification plumbing are deleted (`SplittablePane.swift`) — nothing captures or applies
/// `WindowLayoutSnapshot.splits` any more. The HARD RULE this whole delete sits under: an old
/// saved workspace that still carries populated `splits` must decode WITHOUT ERROR and simply
/// have them ignored — never a crash, never a silent rewrite of the user's saved state. A new
/// suite file per team-lead (new cases stay out of the already-large `WindowWorkspaceTests`).
struct WindowWorkspaceLegacySplitsDecodeTests {

    /// Simulates a workspace saved BEFORE this delete: real `splits` data, encoded honestly by
    /// the (still-`Codable`, decode-only) field, so this is what a pre-slice-F save looks like
    /// on disk today.
    private func legacySnapshotJSON() throws -> Data {
        let legacy = WindowLayoutSnapshot(
            panes: PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: false, showChatPane: false
            ),
            libraryPaneWidth: 320,
            readerPaneWidth: 200,
            chatPaneWidth: 300,
            splits: [
                "reading-reading": PaneSplitCounts(vertical: 2, horizontal: 1),
                "library-library": PaneSplitCounts(vertical: 1, horizontal: 2)
            ],
            viewDisplayMode: "Icon",
            layoutMode: "Widescreen"
        )
        return try JSONEncoder().encode(legacy)
    }

    @Test("an old saved workspace with populated splits decodes without error")
    func oldWorkspaceWithPopulatedSplitsDecodesCleanly() throws {
        let data = try legacySnapshotJSON()
        let decoded = try JSONDecoder().decode(WindowLayoutSnapshot.self, from: data)
        #expect(decoded.splits.count == 2, "the legacy field still decodes its saved values")
    }

    @Test("a whole saved-workspace catalog carrying legacy splits still decodes")
    func catalogWithLegacySplitsDecodes() throws {
        var catalog = WindowWorkspaceCatalog()
        let legacy = try JSONDecoder().decode(WindowLayoutSnapshot.self, from: legacySnapshotJSON())
        catalog.save(name: "Old Save", layout: legacy)

        let data = try catalog.encoded()
        let decoded = WindowWorkspaceCatalog.decoded(from: data)

        #expect(decoded != nil, "a populated legacy splits field must never void the whole catalog")
        #expect(decoded?.workspaces.first?.layout.splits.count == 2, "the legacy values round-trip, even though nothing acts on them any more")
    }
}
