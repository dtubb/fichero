@testable import Fichero
import Foundation
import Testing

/// Right-click Show/Hide Labels on the workflow bar and the markup bar, wired
/// to the SAME setting as the window toolbar's text mode (Daniel, 2026-09-02).
///
/// The risk this guards is not the menu — it is the wiring. A second flag
/// would have looked identical in the screenshot and been wrong: the bars'
/// labels and the toolbar's would drift apart the first time either was used.
struct BarLabelsContextMenuTests {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath),
                   encoding: .utf8)
    }

    @Test("both bars carry the labels context menu")
    func bothBarsCarryTheMenu() throws {
        let workflowBar = try Self.appSource("Views/Shell/Toolbar/WorkflowBar.swift")
        let annotationBar = try Self.appSource("Views/Shell/Toolbar/AnnotationBar.swift")
        for source in [workflowBar, annotationBar] {
            #expect(source.contains("BarLabelsContextMenu("))
            #expect(source.contains("onSetLabels"))
        }
    }

    @Test("both write the one flag the toolbar bridge reads")
    func bothWriteTheSharedFlag() throws {
        let host = try Self.appSource(
            "Views/Shell/ContentView/Layout/ContentView+WorkflowBar.swift")
        // Two call sites, one destination. A second @SceneStorage key here
        // would be the whole bug.
        #expect(host.contains("onSetLabels: { showWorkflowBarLabels = $0 }"))
        #expect(host.components(separatedBy: "onSetLabels: { showWorkflowBarLabels = $0 }")
            .count - 1 == 2)
        #expect(host.contains("ToolbarTextModeSync(showsLabels: $showWorkflowBarLabels)"))
    }

    @Test("the bridge pushes back onto the NSToolbar, not just pulls from it")
    func bridgeIsTwoWay() throws {
        let sync = try Self.appSource(
            "Views/Shell/ContentView/Layout/ToolbarTextModeSync.swift")
        #expect(sync.contains("func apply(showsLabels: Bool)"))
        #expect(sync.contains("toolbar.displayMode = showsLabels ? .iconAndLabel : .iconOnly"))
        #expect(sync.contains("context.coordinator.apply(showsLabels: showsLabels)"))
    }

    @Test("the push compares the labelled reading, so Text Only survives")
    func pushPreservesLabelOnly() throws {
        // `.labelOnly` already means "labelled". Comparing raw modes would
        // rewrite a user's Text Only toolbar to Icon and Text on every update
        // pass — the bridge overruling a choice it was only asked to mirror.
        let sync = try Self.appSource(
            "Views/Shell/ContentView/Layout/ToolbarTextModeSync.swift")
        #expect(sync.contains("guard (toolbar.displayMode != .iconOnly) != showsLabels else { return }"))
    }

    @Test("the menu offers nothing when the host cannot write the setting")
    func menuIsAbsentWithoutAWriter() throws {
        // Same rule as the scope chip and the compare button: an entry that
        // goes nowhere is worse than no entry.
        let menu = try Self.appSource("Views/Shell/Toolbar/BarLabelsContextMenu.swift")
        #expect(menu.contains("if let onSetLabels"))
    }
}
