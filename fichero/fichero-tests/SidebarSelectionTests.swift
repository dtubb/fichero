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
            appSource("Views/Shell/ContentView/Layout/ContentView+Breadcrumb.swift"),
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
}

private func appSource(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("fichero")
        .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
}
