@testable import Fichero
import XCTest

/// Policy tests for window workspaces, layout presets, and split-command
/// routing (Daniel, 2026-08-29 — Xcode 27's window chrome as the model).
/// Pure types only, per the WorkflowBarPolicyTests idiom: serialisation
/// shape, catalog semantics, preset matching, and which SplittablePane a
/// window-level split command addresses.
@MainActor
final class WindowWorkspaceTests: XCTestCase {

    private func snapshot(
        chat: Bool = true,
        splits: [String: PaneSplitCounts] = [:],
        overrides: [String: String] = [:]
    ) -> WindowLayoutSnapshot {
        WindowLayoutSnapshot(
            panes: PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: true, showChatPane: chat
            ),
            libraryPaneWidth: 320,
            readerPaneWidth: 200,
            chatPaneWidth: 300,
            paneKindOverrides: overrides,
            splits: splits,
            viewDisplayMode: "Icon",
            layoutMode: "Widescreen"
        )
    }

    // MARK: - Serialisation shape

    func testSnapshotRoundTripsThroughJSON() throws {
        let original = snapshot(
            splits: ["reading-reading": PaneSplitCounts(vertical: 2, horizontal: 1)],
            overrides: ["preview": "chat"]
        )
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Marshall reading", layout: original)

        let data = try catalog.encoded()
        let decoded = try XCTUnwrap(WindowWorkspaceCatalog.decoded(from: data))
        XCTAssertEqual(decoded, catalog)
        XCTAssertEqual(decoded.workspaces.first?.layout, original)
    }

    func testGarbageDataDecodesToNilNotAnEmptyCatalog() {
        // nil, never a silent empty catalog — the caller decides whether
        // starting fresh is acceptable (prefer-raise rule).
        XCTAssertNil(WindowWorkspaceCatalog.decoded(from: Data("not json".utf8)))
    }

    // MARK: - Catalog semantics

    func testSavingANewNameAppendsAndSortsByName() {
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Writing", layout: snapshot())
        catalog.save(name: "Everything", layout: snapshot())
        XCTAssertEqual(catalog.workspaces.map(\.name), ["Everything", "Writing"])
    }

    func testResavingTheSameNameUpdatesInPlaceKeepingIdentity() {
        var catalog = WindowWorkspaceCatalog()
        let first = catalog.save(name: "Reading", layout: snapshot(chat: true))
        let second = catalog.save(name: "reading", layout: snapshot(chat: false))
        XCTAssertEqual(catalog.workspaces.count, 1)
        XCTAssertEqual(first?.id, second?.id)
        // The re-save's layout and casing win.
        XCTAssertEqual(catalog.workspaces.first?.name, "reading")
        XCTAssertEqual(catalog.workspaces.first?.layout.panes.showChatPane, false)
    }

    func testEmptyAndWhitespaceNamesAreRefused() {
        var catalog = WindowWorkspaceCatalog()
        XCTAssertNil(catalog.save(name: "", layout: snapshot()))
        XCTAssertNil(catalog.save(name: "   \n", layout: snapshot()))
        XCTAssertTrue(catalog.workspaces.isEmpty)
    }

    func testRemoveDeletesExactlyTheNamedWorkspace() throws {
        var catalog = WindowWorkspaceCatalog()
        let keep = catalog.save(name: "Keep", layout: snapshot())
        let drop = catalog.save(name: "Drop", layout: snapshot())
        catalog.remove(id: try XCTUnwrap(drop).id)
        XCTAssertEqual(catalog.workspaces.map(\.id), [try XCTUnwrap(keep).id])
    }

    func testStorePersistsAndReloadsThroughUserDefaults() throws {
        let suiteName = "WindowWorkspaceTests-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }

        let store = WindowWorkspaceStore(defaults: defaults)
        store.save(name: "Morning", layout: snapshot())

        let reloaded = WindowWorkspaceStore(defaults: defaults)
        XCTAssertEqual(reloaded.catalog.workspaces.map(\.name), ["Morning"])

        reloaded.remove(id: try XCTUnwrap(reloaded.catalog.workspaces.first).id)
        let third = WindowWorkspaceStore(defaults: defaults)
        XCTAssertTrue(third.catalog.workspaces.isEmpty)
    }

    // MARK: - Split counts sanitising

    func testSplitCountsAreClampedToWhatTheUICanReach() {
        XCTAssertEqual(
            PaneSplitCounts(vertical: 9, horizontal: 0).sanitized,
            PaneSplitCounts(vertical: 3, horizontal: 1)
        )
        // Both axes live → the 2×2 grid cap, matching SplitPaneState.
        XCTAssertEqual(
            PaneSplitCounts(vertical: 3, horizontal: 2).sanitized,
            PaneSplitCounts(vertical: 2, horizontal: 2)
        )
        XCTAssertFalse(PaneSplitCounts().isSplit)
        XCTAssertTrue(PaneSplitCounts(vertical: 2, horizontal: 1).isSplit)
    }

    // MARK: - Layout presets & split command routing — DELETED (#4685)
    //
    // `WindowLayoutPreset` ("Library Only / Reading / Everything") and `SplitCommandRouting`
    // (the dead `"<slot>-<kind>"` split-key routing) were removed with #4685 — a SECOND
    // built-in arrangement system and a routing table that addressed slot ids the applied
    // renderer never minted. Split now routes through `PaneList.splittingLeaf` directly
    // (`WorkspaceSystemBoundaryTests.testAppliedWorkspaceSplitIsWiredThroughThePaneListModel`);
    // the pure per-leaf split behaviour is covered by `PaneListTests`.

    // MARK: - The applied composition is now part of the snapshot (#4686)

    /// `WindowLayoutSnapshot` used to carry only the legacy `PaneVisibilityPlan` shape — no
    /// `PaneList` — so "Save Current as Workspace…" captured a lie and applying a saved
    /// workspace never touched `activePaneList`. `paneList` is the real composition now.
    func testSnapshotCarriesTheAppliedPaneListThroughJSON() throws {
        let list = PaneList([.leaf(.library), .leaf(.preview), .leaf(.reading)])
        var original = snapshot()
        original.paneList = list
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Reading Desk", layout: original)

        let restored = try XCTUnwrap(WindowWorkspaceCatalog.decoded(from: catalog.encoded()))
        XCTAssertEqual(restored.workspaces.first?.layout.paneList, list)
        // Ids round-trip too — identity matters (a saved workspace re-applies the SAME leaves).
        XCTAssertEqual(restored.workspaces.first?.layout.paneList?.nodes.map(\.id), list.nodes.map(\.id))
    }

    /// A snapshot saved BEFORE #4686 has no `paneList` key at all — it must still decode, with
    /// `paneList == nil`, rather than throwing away the user's whole catalog (the same lenient
    /// contract every field added since `WindowLayoutSnapshot` shipped has honoured).
    func testAnOldShapeSnapshotDecodesWithPaneListNil() throws {
        let json = """
        {"panes":{"showSidebar":true,"showInspector":false,"showLibraryPane":true,
        "showPreviewPane":true,"showReaderPane":true,"showChatPane":false},
        "libraryPaneWidth":320,"readerPaneWidth":200,"chatPaneWidth":300,
        "viewDisplayMode":"Icon","layoutMode":"Widescreen"}
        """
        let decoded = try JSONDecoder().decode(WindowLayoutSnapshot.self, from: Data(json.utf8))
        XCTAssertNil(decoded.paneList)
    }

    /// SF10 review finding: a PRESENT-but-malformed `paneList` used to THROW out of
    /// `init(from:)` — unlike absence, which `decodeIfPresent` alone already handles — and that
    /// throw propagated through `JSONDecoder().decode(WindowLayoutSnapshot.self, ...)`. The
    /// malformed value must degrade to `nil` (this one snapshot falls back to Read on apply)
    /// exactly like absence does, not throw.
    func testASnapshotWithMalformedPaneListDataStillDecodesWithPaneListNil() throws {
        let json = """
        {"panes":{"showSidebar":true,"showInspector":false,"showLibraryPane":true,
        "showPreviewPane":true,"showReaderPane":true,"showChatPane":false},
        "libraryPaneWidth":320,"readerPaneWidth":200,"chatPaneWidth":300,
        "viewDisplayMode":"Icon","layoutMode":"Widescreen",
        "paneList":"this is not a PaneList"}
        """
        let decoded = try JSONDecoder().decode(WindowLayoutSnapshot.self, from: Data(json.utf8))
        XCTAssertNil(decoded.paneList)
        // The REST of the snapshot survived the malformed field — it wasn't just "give up".
        XCTAssertEqual(decoded.libraryPaneWidth, 320)
        XCTAssertTrue(decoded.panes.showLibraryPane)
    }

    /// The actual SF10 bug: one saved workspace with malformed pane data used to void the WHOLE
    /// catalog (`WindowWorkspaceCatalog.decoded(from:)` swallows any decode throw to `nil`),
    /// deleting every OTHER saved workspace along with it.
    func testOneWorkspaceWithMalformedPaneListDoesNotDeleteTheRestOfTheCatalog() throws {
        let goodList = PaneList([.leaf(.library), .leaf(.reading)])
        var good = snapshot()
        good.paneList = goodList
        var bad = snapshot()
        let badList = PaneList([.leaf(.preview)])
        bad.paneList = badList

        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Good", layout: good)
        catalog.save(name: "Bad", layout: bad)

        var json = try XCTUnwrap(String(data: catalog.encoded(), encoding: .utf8))
        // Corrupt ONLY "Bad"'s paneList value in place — computed the same way it was encoded, so
        // this is a targeted single-field corruption, not a hand-written guess at the JSON shape.
        let badPaneListJSON = try XCTUnwrap(String(data: JSONEncoder().encode(badList), encoding: .utf8))
        XCTAssertTrue(json.contains(badPaneListJSON), "test setup: expected Bad's encoded paneList verbatim in the catalog")
        json = json.replacingOccurrences(of: badPaneListJSON, with: "\"not a pane list\"")

        let restored = WindowWorkspaceCatalog.decoded(from: try XCTUnwrap(json.data(using: .utf8)))
        XCTAssertNotNil(restored, "A malformed paneList anywhere must not void the whole catalog.")
        XCTAssertEqual(Set(restored?.workspaces.map(\.name) ?? []), ["Bad", "Good"])
        XCTAssertEqual(restored?.workspaces.first { $0.name == "Good" }?.layout.paneList, goodList)
        XCTAssertNil(restored?.workspaces.first { $0.name == "Bad" }?.layout.paneList)
    }

    // MARK: - Toolbar visibility (Daniel, 2026-08-31)

    func testSnapshotCarriesTheToolbarConfigurationThroughJSON() throws {
        var original = snapshot()
        original.toolbar = .minimal
        original.showWorkflowBar = true
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Desk", layout: original)

        let restored = try XCTUnwrap(
            WindowWorkspaceCatalog.decoded(from: catalog.encoded())
        )
        XCTAssertEqual(restored.workspaces.first?.layout.toolbar, .minimal)
        XCTAssertEqual(restored.workspaces.first?.layout.showWorkflowBar, true)
    }

    /// A workspace saved BEFORE the toolbar fields existed must still decode —
    /// the alternative is `decoded(from:)` returning nil and every saved
    /// layout the user has silently disappearing.
    func testLegacySnapshotWithoutToolbarFieldsStillDecodes() throws {
        let panes = #"{"showSidebar":true,"showInspector":false,"#
            + #""showLibraryPane":true,"showPreviewPane":true,"#
            + #""showReaderPane":true,"showChatPane":true}"#
        let legacy = #"{"panes":"# + panes
            + #","libraryPaneWidth":320,"readerPaneWidth":200,"chatPaneWidth":300,"#
            + #""viewDisplayMode":"Icon","layoutMode":"Widescreen"}"#
        let decoded = try JSONDecoder().decode(
            WindowLayoutSnapshot.self,
            from: Data(legacy.utf8)
        )
        XCTAssertEqual(decoded.toolbar, .everything)
        XCTAssertFalse(decoded.showWorkflowBar)
        XCTAssertTrue(decoded.paneKindOverrides.isEmpty)
        XCTAssertTrue(decoded.splits.isEmpty)
    }

    func testMinimalToolbarKeepsNavigationAndPanesAndDropsTheArrangingMenus() {
        XCTAssertTrue(ToolbarVisibilityPlan.minimal.showNavigation)
        XCTAssertTrue(ToolbarVisibilityPlan.minimal.showPaneToggles)
        XCTAssertFalse(ToolbarVisibilityPlan.minimal.showSplitMenu)
        XCTAssertFalse(ToolbarVisibilityPlan.minimal.showLayoutsMenu)
    }

    // The built-in workspaces are now the v2 PaneList compositions
    // (`BuiltInWorkspaceLayout`), covered by `BuiltInWorkspaceLayoutTests`. The
    // legacy `BuiltInWorkspace` show/hide presets — and the tests that pinned
    // their pane sets, bars and ⌘⌥ slots — were retired with the enum (spec
    // workspaces.one-system). Snapshot/saved-workspace tests below still stand.

    // MARK: - The markup bar is part of the arrangement (Daniel, 2026-09-02)

    func testSnapshotCarriesBothWindowBars() throws {
        // Applying a workspace "doesn't seem to do much" was, in part, this:
        // the markup bar was the one piece of window chrome a workspace named
        // nothing about, so a reading desk saved with it up came back without.
        var original = snapshot()
        original.showWorkflowBar = true
        original.showAnnotationBar = true
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Marking Up", layout: original)
        let restored = WindowWorkspaceCatalog.decoded(from: try catalog.encoded())
        XCTAssertEqual(restored?.workspaces.first?.layout.showAnnotationBar, true)
        XCTAssertEqual(restored?.workspaces.first?.layout.showWorkflowBar, true)
    }

    func testAWorkspaceSavedBeforeTheMarkupBarStillDecodes() throws {
        // Lenient decode, same contract as every field added since: an old
        // saved layout must not throw away the user's whole catalog.
        let json = """
        {"panes":{"showSidebar":true,"showInspector":false,"showLibraryPane":true,
        "showPreviewPane":true,"showReaderPane":false,"showChatPane":false},
        "libraryPaneWidth":320,"readerPaneWidth":200,"chatPaneWidth":300,
        "viewDisplayMode":"Icon","layoutMode":"Widescreen"}
        """
        let decoded = try JSONDecoder().decode(
            WindowLayoutSnapshot.self, from: Data(json.utf8))
        XCTAssertFalse(decoded.showAnnotationBar)
        XCTAssertFalse(decoded.showWorkflowBar)
    }

    // MARK: - Menu rows carry a glyph

    func testSavedWorkspacesDeriveAGlyphAndNeverStoreOne() {
        // Derived, never persisted: an icon picked at save time goes stale the
        // moment the workspace is re-saved over.
        var reading = snapshot(chat: false)
        reading.panes.showPreviewPane = false
        XCTAssertEqual(
            SavedWindowWorkspace(id: UUID(), name: "R", savedAt: Date(), layout: reading)
                .systemImage,
            "book")
        var cataloguing = snapshot(chat: false)
        cataloguing.panes.showReaderPane = false
        cataloguing.showWorkflowBar = true
        XCTAssertEqual(
            SavedWindowWorkspace(id: UUID(), name: "C", savedAt: Date(), layout: cataloguing)
                .systemImage,
            "tray.full")
        let withChat = SavedWindowWorkspace(
            id: UUID(), name: "E", savedAt: Date(), layout: snapshot(chat: true))
        XCTAssertEqual(withChat.systemImage, "sparkles.rectangle.stack")
        // Every workspace gets SOME glyph — a menu with one bare row is worse
        // than a menu with none.
        XCTAssertFalse(withChat.systemImage.isEmpty)
    }

    func testTheRowTooltipListsWhatWillBeRestored() {
        var layout = snapshot(
            splits: ["reading-reading": PaneSplitCounts(vertical: 2, horizontal: 1)])
        layout.showAnnotationBar = true
        let workspace = SavedWindowWorkspace(
            id: UUID(), name: "Marking Up", savedAt: Date(), layout: layout)
        let help = workspace.help
        XCTAssertTrue(help.hasPrefix("Restores:"))
        XCTAssertTrue(help.contains("reader"))
        XCTAssertTrue(help.contains("markup bar"))
        XCTAssertTrue(help.contains("1 split pane"))
    }

    // MARK: - Rename (the Workspace Manager's rename field)

    func testRenameChangesTheNameKeepingIdentityAndLayout() throws {
        var catalog = WindowWorkspaceCatalog()
        let saved = catalog.save(name: "Draft", layout: snapshot())
        let id = try XCTUnwrap(saved).id
        let renamed = catalog.rename(id: id, to: "  Final  ")
        XCTAssertEqual(renamed?.id, id, "identity survives a rename")
        XCTAssertEqual(renamed?.name, "Final", "the new name is trimmed")
        XCTAssertEqual(catalog.workspaces.first { $0.id == id }?.name, "Final")
    }

    func testRenameRefusesEmptyAndLeavesTheCatalogUnchanged() throws {
        var catalog = WindowWorkspaceCatalog()
        let id = try XCTUnwrap(catalog.save(name: "Keep", layout: snapshot())).id
        XCTAssertNil(catalog.rename(id: id, to: "   "))
        XCTAssertEqual(catalog.workspaces.first { $0.id == id }?.name, "Keep")
    }

    func testRenameRefusesANameAnotherWorkspaceAlreadyWears() throws {
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Reading", layout: snapshot())
        let id = try XCTUnwrap(catalog.save(name: "Cataloguing", layout: snapshot())).id
        // Case-insensitive collision — the confusing-twin guard save() uses.
        XCTAssertNil(catalog.rename(id: id, to: "reading"))
        XCTAssertEqual(catalog.workspaces.first { $0.id == id }?.name, "Cataloguing")
        XCTAssertEqual(catalog.workspaces.count, 2)
    }

    func testRenameAnUnknownIdIsANoOp() {
        var catalog = WindowWorkspaceCatalog()
        catalog.save(name: "Only", layout: snapshot())
        XCTAssertNil(catalog.rename(id: UUID(), to: "Whatever"))
        XCTAssertEqual(catalog.workspaces.map(\.name), ["Only"])
    }
}
