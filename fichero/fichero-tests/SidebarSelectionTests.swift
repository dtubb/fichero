@testable import Fichero
import Foundation
import Testing

struct SidebarSelectionTests {
    @Test("#1165 sidebar tap fallback ignores already-selected rows")
    func tapFallbackIgnoresCurrentSelection() {
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:1") == nil)
    }

    @Test("sidebar destination parses and serializes document ids")
    func destinationRoundTripDocument() {
        let destination = try #require(SidebarDestination(serializedID: "doc:abc"))
        #expect(destination == .document("abc"))
        #expect(destination.serializedID == "doc:abc")
    }

    @Test("sidebar destination parses browser sentinels")
    func destinationParsesBrowserSentinel() {
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
        let stateSource = try appSource("Views/ContentView+State.swift")
        let navigationSource = try appSource("Views/ContentView+Navigation.swift")
        let displayModeSource = try appSource("Views/Library/LibraryView+DisplayModes.swift")
        let componentSource = try appSource("Views/Library/LibraryViewComponents.swift")

        #expect(stateSource.contains("browserSelection.removeAll()"))
        #expect(navigationSource.contains("isPaneFocused: focusedPane == .content"))
        #expect(displayModeSource.contains("private var selectionTint: Color"))
        #expect(displayModeSource.contains("isPaneFocused ? .accentColor : .secondary"))
        #expect(componentSource.contains("var selectedTint: Color = .accentColor"))
    }

    @Test("#2547 compact inspector sheet defaults to full-height .large")
    func compactInspectorSheetDefaultsToLarge() throws {
        // The sheet must NOT default to [.medium, .large] (which opens at 50%);
        // it should default to a single .large detent so iPhone opens full-height.
        let source = try appSource("Views/Library/InspectorPresenter.swift")
        #expect(source.contains("detents: Set<PresentationDetent> = [.large]"))
        #expect(!source.contains("[.medium, .large]"))
    }

    @Test("#1736 Open in New Tab captures the originating window before opening")
    func openInNewTabCapturesHostWindowBeforeOpen() throws {
        let source = try appSource("Views/OpenAffordances.swift")
        let hostCapture = try #require(source.range(of: "let hostWindow = NSApp.keyWindow ?? NSApp.mainWindow"))
        // Prefix with indentation to skip the docstring comment at line 34 and match the code call.
        let openCall = try #require(source.range(of: "\n            openWindow(id: \"main\")"))

        #expect(hostCapture.lowerBound < openCall.lowerBound)
        #expect(source.contains("hostWindow.addTabbedWindow(newWindow, ordered: .above)"))
    }

    @Test("#1736 Open in New Window disables automatic tabbing")
    func openInNewWindowDisablesAutomaticTabbing() throws {
        let source = try appSource("Views/OpenAffordances.swift")

        #expect(source.contains("NSWindow.allowsAutomaticWindowTabbing = false"))
        #expect(source.contains("newWindow.tabbingMode = .disallowed"))
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
