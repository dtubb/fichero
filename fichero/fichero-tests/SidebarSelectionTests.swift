@testable import Fichero
import Foundation
import Testing

struct SidebarSelectionTests {
    @Test("#1165 sidebar tap fallback ignores already-selected rows")
    func tapFallbackIgnoresCurrentSelection() {
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:1") == nil)
    }

    @Test("sidebar destination parses and serializes document ids")
    func destinationRoundTripDocument() throws {
        let destination = try #require(SidebarDestination(serializedID: "doc:abc"))
        #expect(destination == .document("abc"))
        #expect(destination.serializedID == "doc:abc")
    }

    @Test("#11 workflow/search/chat folder ids round-trip through the destination")
    func destinationRoundTripVirtualFolder() throws {
        // Virtual section folders use id "folder:<path>:<Category>". Before #11
        // the `folder:` prefix wasn't parsed, so `SidebarItem.destination` fell
        // back to `.document(id)` and `serializedID` mangled it into
        // "doc:folder:…" — `findItemById` never matched → clicking the folder
        // routed to nothing.
        let destination = try #require(SidebarDestination(serializedID: "folder:/flows:Workflow"))
        #expect(destination == .folder("/flows:Workflow"))
        #expect(destination.serializedID == "folder:/flows:Workflow")
    }

    @Test("#11 a workflow folder item's destination resolves back to its own id")
    func workflowFolderItemDestinationMatchesId() {
        // The click path is: row tag = item.destination → its serializedID is fed
        // to findItemById(id:). If serializedID != item.id, the lookup misses and
        // handleSelection(nil) shows nothing. This is the exact regression the
        // folder-nav bug produced.
        let folder = SidebarItem.folder(
            name: "Flows", folderPath: "/flows", category: .workflow, libraryId: UUID()
        )
        #expect(folder.destination.serializedID == folder.id)
        // The same must hold for saved-search and chat section folders.
        let searchFolder = SidebarItem.folder(
            name: "Saved", folderPath: "/s", category: .search, libraryId: UUID()
        )
        #expect(searchFolder.destination.serializedID == searchFolder.id)
        let chatFolder = SidebarItem.folder(
            name: "Threads", folderPath: "/c", category: .chat, libraryId: UUID()
        )
        #expect(chatFolder.destination.serializedID == chatFolder.id)
    }

    @Test("sidebar destination parses browser sentinels")
    func destinationParsesBrowserSentinel() throws {
        let destination = try #require(SidebarDestination(serializedID: "activity-browser"))
        #expect(destination == .browser(.activity))
        #expect(destination.serializedID == "activity-browser")
    }

    @Test("selection state keeps string persistence as a bridge")
    @MainActor
    func selectionStateBridgesTypedAndStringSelection() {
        let state = SidebarSelectionState()
        state.selectedItemId = "workflow:wf-1"
        #expect(state.selectedDestination == .workflow("wf-1"))
        state.selectedDestination = .browser(.research)
        #expect(state.selectedItemId == "research-browser")
    }

    @Test("#1165 sidebar tap fallback only requests missing selection")
    func tapFallbackRequestsDifferentSelection() {
        #expect(sidebarSelectionFallback(current: nil, tapped: "doc:1") == "doc:1")
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:2") == "doc:2")
    }

    @Test("#2548 restored selection that was never handled is reconciled")
    func restoredUnhandledSelectionReconciles() {
        // Launch: @SceneStorage restored selectedItemId, but onChange never fired
        // (value didn't change) so lastHandled is still nil → must reconcile.
        #expect(sidebarShouldReconcileSelection(selectedId: "doc:1", lastHandled: nil))
        // Browser tags restore the same way.
        #expect(sidebarShouldReconcileSelection(selectedId: "activity-browser", lastHandled: nil))
    }

    @Test("#2548 already-handled selection is not reconciled again")
    func handledSelectionDoesNotReconcile() {
        // Once handleSelectionChange has run for an id, reconcile must be a no-op
        // so the reconcile path never double-handles a live click.
        #expect(!sidebarShouldReconcileSelection(selectedId: "doc:1", lastHandled: "doc:1"))
    }

    @Test("#2548 no selection means nothing to reconcile")
    func noSelectionDoesNotReconcile() {
        #expect(!sidebarShouldReconcileSelection(selectedId: nil, lastHandled: nil))
        #expect(!sidebarShouldReconcileSelection(selectedId: nil, lastHandled: "doc:1"))
    }

    @Test("#2522 sidebar selection clears library selection and content uses pane focus tint")
    func sidebarAndLibrarySelectionStayInSync() throws {
        let stateSource = try [
            appSource("Views/Shell/ContentView/ContentView+StateDisplay.swift"),
            appSource("Views/Shell/ContentView/ContentView+StateSelection.swift"),
            appSource("Views/Shell/ContentView/ContentView+StateLayout.swift"),
            appSource("Views/Shell/ContentView/ContentView+StatePreview.swift"),
            appSource("Views/Shell/ContentView/ContentView+StateEvents.swift"),
        ].joined(separator: "\n")
        let navigationSource = try appSource("Views/Shell/ContentView/ContentView+Navigation.swift")
        // selectionTint moved to LibraryView+DisplayHelpers and was promoted private→internal
        // when LibraryView+DisplayModes was split by file_length.
        let displayHelpersSource = try appSource("Views/Library/ViewModes/LibraryView+DisplayHelpers.swift")
        // #4024: selectedTint default now lives in LibraryThumbnailViews.swift (DocumentThumbnailView split out).
        let componentSource = try appSource("Views/Library/LibraryThumbnailViews.swift")

        #expect(stateSource.contains("browserSelection.removeAll()"))
        #expect(navigationSource.contains("isPaneFocused: focusedPane == .content"))
        #expect(displayHelpersSource.contains("var selectionTint: Color"))
        #expect(displayHelpersSource.contains("isPaneFocused ? .accentColor : .secondary"))
        #expect(componentSource.contains("var selectedTint: Color = .accentColor"))
    }

    @Test("#3406 active split drives location chrome and inspector can claim focus")
    func splitFocusDrivesLocationChrome() throws {
        let stateSource = try [
            appSource("Views/Shell/ContentView/ContentView+StateDisplay.swift"),
            appSource("Views/Shell/ContentView/ContentView+StateSelection.swift"),
            appSource("Views/Shell/ContentView/ContentView+StateLayout.swift"),
            appSource("Views/Shell/ContentView/ContentView+StatePreview.swift"),
            appSource("Views/Shell/ContentView/ContentView+StateEvents.swift"),
        ].joined(separator: "\n")
        let buildersSource = try ([
            appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))

        #expect(stateSource.contains("var activeLocationDocument: Document?"))
        #expect(stateSource.contains("switch focusedPane"))
        #expect(stateSource.contains("pageFocusDocument ?? detailDocument ?? inspectorDocument"))
        #expect(stateSource.contains("if let page = activeLocationDocument, page.docType == .page"))
        #expect(buildersSource.contains(".simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .inspector })"))
    }

    @Test("#2547 compact inspector sheet defaults to full-height .large")
    func compactInspectorSheetDefaultsToLarge() throws {
        // The sheet must NOT default to [.medium, .large] (which opens at 50%);
        // it should default to a single .large detent so iPhone opens full-height.
        let source = try appSource("Views/Inspector/InspectorPresenter.swift")
        #expect(source.contains("detents: Set<PresentationDetent> = [.large]"))
        #expect(!source.contains("[.medium, .large]"))
    }

    @Test("#1736 Open in New Tab captures the originating window before opening")
    func openInNewTabCapturesHostWindowBeforeOpen() throws {
        let source = try appSource("Views/Shell/OpenAffordances.swift")
        let hostCapture = try #require(source.range(of: "let hostWindow = NSApp.keyWindow ?? NSApp.mainWindow"))
        // Prefix with indentation to skip the docstring comment at line 34 and match the code call.
        let openCall = try #require(source.range(of: "\n            openWindow(id: \"main\")"))

        #expect(hostCapture.lowerBound < openCall.lowerBound)
        #expect(source.contains("hostWindow.addTabbedWindow(newWindow, ordered: .above)"))
    }

    @Test("#1736 Open in New Window disables automatic tabbing")
    func openInNewWindowDisablesAutomaticTabbing() throws {
        let source = try appSource("Views/Shell/OpenAffordances.swift")

        #expect(source.contains("NSWindow.allowsAutomaticWindowTabbing = false"))
        #expect(source.contains("newWindow.tabbingMode = .disallowed"))
    }

    @Test("#4062 New Tab does not flash a transient window")
    func newTabDoesNotCreateTransientWindow() throws {
        // The host's tabbingMode must be set to .preferred BEFORE the openWindow
        // call so macOS merges the new window directly into the tab group as it's
        // created — instead of flashing a separate window first, then merging.
        let source = try appSource("Views/Shell/OpenAffordances.swift")
        let tabModeSet = try #require(
            source.range(of: "hostWindow?.tabbingMode = .preferred")
        )
        let openCall = try #require(source.range(of: "\n            openWindow(id: \"main\")"))

        #expect(tabModeSet.lowerBound < openCall.lowerBound)
        // The belt-and-suspenders merge must remain for cases where auto-tab didn't fire.
        #expect(source.contains("hostWindow.addTabbedWindow(newWindow, ordered: .above)"))
    }

    @Test("#4062 New Library creates in-place, does not open a new window")
    func newLibraryDoesNotOpenNewWindow() throws {
        // handleNewLibrary must switch the CURRENT window to the new library
        // (assignLibrary), not open a fresh window via WindowOpener. New Window
        // is the only new-window path; New Library is an in-place create.
        let source = try appSource("App/LibraryWindow+Actions.swift")
        let functionStart = try #require(source.range(of: "func handleNewLibrary() {"))
        let nextFunction = try #require(
            source.range(of: "func handleSaveLibrary() {", range: functionStart.lowerBound..<source.endIndex)
        )
        let functionBody = String(source[functionStart.lowerBound..<nextFunction.lowerBound])

        #expect(functionBody.contains("assignLibrary(id: newLibrary.id)"))
        #expect(!functionBody.contains("WindowOpener.open"))
        #expect(!functionBody.contains("openWindow(id:"))
    }

    @Test("#4062 NewLibraryActionKey docstring reflects in-place create, not new window")
    func newLibraryActionKeyDocstringReflectsInPlace() throws {
        let source = try appSource("App/Menus/FocusedCommandButtons+FocusedValues.swift")
        let keyStart = try #require(source.range(of: "struct NewLibraryActionKey: FocusedValueKey {"))
        // The docstring block sits immediately above the struct declaration.
        let sliceThroughKey = String(source[source.startIndex..<keyStart.upperBound])

        #expect(sliceThroughKey.contains("in-place"))
        #expect(sliceThroughKey.contains("no new window"))
        #expect(!sliceThroughKey.contains("opening it in a new window"))
    }

    @Test("#3364 library double-click opens in the current window")
    func libraryDoubleClickOpensInCurrentWindow() throws {
        // #4024: handleDoubleClick/handleTap moved to LibraryView+Selection.swift.
        let source = try appSource("Views/Library/LibraryView+Selection.swift")
        let functionStart = try #require(source.range(of: "func handleDoubleClick(_ doc: Document) {"))
        let nextFunction = try #require(
            source.range(of: "func handleTap(_ doc: Document) {", range: functionStart.lowerBound..<source.endIndex)
        )
        let functionBody = String(source[functionStart.lowerBound..<nextFunction.lowerBound])

        #expect(functionBody.contains("listScrollCenterTarget = doc.id"))
        #expect(functionBody.contains("openDocument(doc)"))
        #expect(!functionBody.contains("openDocumentInNewWindow(doc, asTab: false)"))
    }

    // MARK: - Multi-select (contiguous / discontiguous)

    @Test("empty selection routes to no primary")
    func primaryEmptyIsNil() {
        #expect(sidebarPrimaryDestination(for: [], previous: .document("x")) == nil)
    }

    @Test("single selection routes to that row")
    func primarySingleRoutes() {
        #expect(sidebarPrimaryDestination(for: [.document("a")], previous: nil) == .document("a"))
    }

    @Test("batch selection keeps the previous primary while it stays selected")
    func primaryBatchKeepsStablePrimary() {
        let selection: Set<SidebarDestination> = [.document("a"), .document("b")]
        // previous (a) is still in the set → detail must not thrash.
        #expect(sidebarPrimaryDestination(for: selection, previous: .document("a")) == .document("a"))
    }

    @Test("removing the primary from a batch falls back to a remaining member")
    func primaryBatchFallsBackWhenPrimaryRemoved() throws {
        // Was {a,b,c}, user cmd-clicked a off → {b,c}. Previous (a) is gone, so
        // the primary must be one of the still-highlighted rows, never `a`.
        let selection: Set<SidebarDestination> = [.document("b"), .document("c")]
        let primary = try #require(sidebarPrimaryDestination(for: selection, previous: .document("a")))
        #expect(primary != .document("a"))
        #expect(selection.contains(primary))
    }

    @Test("batch selection with no previous primary picks a selected member")
    func primaryBatchNoPreviousPicksMember() {
        let selection: Set<SidebarDestination> = [.search("q1"), .search("q2")]
        let primary = sidebarPrimaryDestination(for: selection, previous: nil)
        #expect(primary != nil)
        #expect(selection.contains(primary ?? .document("none")))
    }

    @Test("collapse returns the single anchor, or empty for none")
    func collapseToAnchor() {
        #expect(sidebarCollapsedSelection(primary: nil).isEmpty)
        #expect(sidebarCollapsedSelection(primary: .document("a")) == [.document("a")])
    }

    @Test("programmatic single-selection drives the highlight set to that one row")
    @MainActor
    func programmaticSelectionSyncsHighlightSet() {
        let state = SidebarSelectionState()
        state.selectedItemId = "doc:a"
        #expect(state.selectedDestinations == [.document("a")])
        // Re-selecting a different row replaces (does not accumulate).
        state.selectedItemId = "search:q"
        #expect(state.selectedDestinations == [.search("q")])
        // Clearing the routed selection clears the highlight too.
        state.selectedItemId = nil
        #expect(state.selectedDestinations.isEmpty)
    }

    @Test("#3187 library browser surfaces keep a shared leading inset clear of the sidebar")
    func libraryBrowserUsesSharedLeadingInset() throws {
        // browserLeadingInset is defined in LibraryView+DisplayHelpers and consumed by the
        // icon grid in LibraryView+IconMode (file_length split of LibraryView+DisplayModes).
        let displayHelpersSource = try appSource("Views/Library/ViewModes/LibraryView+DisplayHelpers.swift")
        let iconModeSource = try appSource("Views/Library/ViewModes/LibraryView+IconMode.swift")
        let tableSource = try appSource("Views/Library/ViewModes/LibraryView+TableView.swift")

        #expect(displayHelpersSource.contains("var browserLeadingInset: CGFloat { 12 }"))
        #expect(iconModeSource.contains(".padding(.leading, browserLeadingInset)"))
        #expect(tableSource.contains(".padding(.leading, browserLeadingInset)"))
    }

    @Test("FocusedLibraryAction equality ignores the closure so focus republish short-circuits")
    func focusedLibraryActionEqualityShortCircuits() {
        // Distinct closure instances must not defeat equality — a raw closure
        // focused value caused an AttributeGraph invalidation storm (launch
        // hang / AG::LayoutDescriptor::Compare crash) when a persisted
        // selection restored.
        var hits = 0
        let first = FocusedLibraryAction(isEnabled: true) { hits += 1 }
        let second = FocusedLibraryAction(isEnabled: true) { hits += 2 }
        #expect(first == second)
        #expect(FocusedLibraryAction(isEnabled: true) {} != FocusedLibraryAction(isEnabled: false) {})
        second.run()
        #expect(hits == 2)
    }

    @Test("no FocusedValueKey publishes a raw closure Value")
    func noRawClosureFocusedValueKeys() throws {
        // Every focused value must be an Equatable wrapper. A bare
        // `typealias Value = () -> Void` key is byte-compared by AttributeGraph
        // and re-invalidates every body pass (RunWorkflowOnSelectionKey was the
        // one outlier; keep it at zero).
        let focusedValuesSource = try appSource("App/Menus/FocusedCommandButtons+FocusedValues.swift")
        #expect(!focusedValuesSource.contains("typealias Value = () -> Void"))
        #expect(!focusedValuesSource.contains("typealias Value = (() -> Void)"))
    }

    @Test("failed selection resolution un-stamps lastHandled so restore reconciles (#2548)")
    func failedResolutionUnstampsForReconcile() throws {
        // Launch-restore resolves before caches exist; if the destination
        // stays stamped as handled, reconcileRestoredSelection() never
        // re-drives it and the restored row never routes to its detail view.
        let handlingSource = try appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift")
        let defaultCase = try #require(
            handlingSource.range(of: "let item = findItemById(destination.serializedID, in: allCachedItems)")
        )
        let afterLookup = handlingSource[defaultCase.upperBound...]
        #expect(afterLookup.contains("lastHandledSelectionDestination = nil"))
        // And the retry itself stays live: an un-stamped selection reconciles.
        #expect(sidebarShouldReconcileSelection(selectedId: "doc:1", lastHandled: nil))
    }
}

private func appSource(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("fichero")
        .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
}
