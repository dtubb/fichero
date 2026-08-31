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

    // MARK: - Presets

    func testPresetMatchingIsExactOnTheSixFlags() {
        let reading = PaneVisibilityPlan(
            showSidebar: true, showInspector: false,
            showLibraryPane: true, showPreviewPane: true,
            showReaderPane: true, showChatPane: false
        )
        XCTAssertTrue(WindowLayoutPreset.reading.matches(reading))
        XCTAssertFalse(WindowLayoutPreset.everything.matches(reading))
        XCTAssertFalse(WindowLayoutPreset.libraryOnly.matches(reading))
    }

    func testEveryPresetPlanKeepsAContentPaneVisible() {
        // The #1696 invariant in preset form: a preset that hid every content
        // pane could never be applied.
        for preset in WindowLayoutPreset.allCases {
            XCTAssertTrue(preset.plan.isValid, "\(preset) hides every content pane")
        }
    }

    // MARK: - Split command routing

    private let fourSlots: [(id: String, kind: String)] = [
        ("library", "library"), ("preview", "preview"),
        ("reading", "reading"), ("chat", "chat")
    ]

    func testFocusedPaneResolvesToItsSlotScopedStorageKey() {
        XCTAssertEqual(
            SplitCommandRouting.storageKey(focus: .content, slots: fourSlots, overrides: [:]),
            "library-library"
        )
        XCTAssertEqual(
            SplitCommandRouting.storageKey(focus: .chat, slots: fourSlots, overrides: [:]),
            "chat-chat"
        )
    }

    func testKindOverrideRedirectsTheCommandToTheHostingSlot() {
        // The preview SLOT hosts a chat (Daniel 2026-08-23 slot switching):
        // a focused chat must address "preview-chat" — the key the live
        // layout mints — not the absent "chat-chat".
        let slots: [(id: String, kind: String)] = [("library", "library"), ("preview", "preview")]
        XCTAssertEqual(
            SplitCommandRouting.storageKey(
                focus: .chat, slots: slots, overrides: ["preview": "chat"]
            ),
            "preview-chat"
        )
        // …and the slot's PLANNED kind no longer answers for preview focus.
        XCTAssertNil(
            SplitCommandRouting.storageKey(
                focus: .preview, slots: slots, overrides: ["preview": "chat"]
            )
        )
    }

    func testNonSplittableFocusAndAbsentPanesResolveToNil() {
        XCTAssertNil(SplitCommandRouting.storageKey(focus: .sidebar, slots: fourSlots, overrides: [:]))
        XCTAssertNil(SplitCommandRouting.storageKey(focus: .inspector, slots: fourSlots, overrides: [:]))
        XCTAssertNil(SplitCommandRouting.storageKey(focus: nil, slots: fourSlots, overrides: [:]))
        // Chat hidden → no slot hosts chat → nothing to split.
        XCTAssertNil(SplitCommandRouting.storageKey(
            focus: .chat, slots: [("library", "library")], overrides: [:]
        ))
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

    // MARK: - Built-in workspaces

    func testBuiltInWorkspacesAreValidPaneSets() {
        for workspace in BuiltInWorkspace.allCases {
            XCTAssertTrue(
                workspace.panes.isValid,
                "\(workspace.title) hides every content pane — #1696 refuses it"
            )
        }
    }

    func testCataloguingIsTheOnlyBuiltInThatBringsTheWorkflowBar() {
        XCTAssertTrue(BuiltInWorkspace.cataloguing.showsWorkflowBar)
        XCTAssertFalse(BuiltInWorkspace.reading.showsWorkflowBar)
        XCTAssertFalse(BuiltInWorkspace.everything.showsWorkflowBar)
    }

    func testBuiltInMatchesOnlyWhenPanesToolbarAndBarAllAgree() {
        let reading = BuiltInWorkspace.reading
        XCTAssertTrue(reading.matches(
            panes: reading.panes, toolbar: reading.toolbar, workflowBar: false
        ))
        // Same panes, but the user turned the Layouts button back on.
        XCTAssertFalse(reading.matches(
            panes: reading.panes, toolbar: .everything, workflowBar: false
        ))
        // Same panes and toolbar, but the workflow bar is up.
        XCTAssertFalse(reading.matches(
            panes: reading.panes, toolbar: reading.toolbar, workflowBar: true
        ))
    }

    func testBuiltInsAreDistinctArrangements() {
        let plans = BuiltInWorkspace.allCases.map(\.panes)
        XCTAssertEqual(Set(BuiltInWorkspace.allCases.map(\.title)).count, 3)
        XCTAssertNotEqual(plans[0], plans[1])
        XCTAssertNotEqual(plans[1], plans[2])
    }
}
