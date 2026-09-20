@testable import Fichero
import Testing

/// #4968: the View menu's Workspaces flyout and the toolbar's Workspaces menu must be built from
/// ONE definition (`WorkspacesMenuBody`) — same items, wording, order, shortcuts and enabled
/// state — instead of two hand-built menus that can drift, as the issue's own evidence showed
/// (icons, shortcuts, Save wording, and Split's enabled state all differing).
struct WorkspacesMenuOneDefinitionTests {

    // MARK: - Both menus render the SAME shared body — not a source scan of two independent
    // implementations that happen to look alike, but a check that both call sites construct the
    // one type. There is no ViewInspector or similar in this target (checked before writing this
    // file), so this is a structural check, not a mounted render; it proves the two CANNOT list
    // different items (there is only one `body`), not that either renders correctly on screen.

    @Test("the View menu's WorkspaceCommandsSection renders WorkspacesMenuBody")
    func viewMenuRendersTheSharedBody() throws {
        let source = try AppSource.code("App/Menus/ViewMenuPaneSections.swift")
        let body = try #require(
            source.components(separatedBy: "struct WorkspaceCommandsSection: View {").dropFirst().first
        )
        #expect(body.contains("WorkspacesMenuBody(commands: commands)"))
    }

    @Test("the toolbar's workspacesMenu renders the same WorkspacesMenuBody")
    func toolbarMenuRendersTheSharedBody() throws {
        let source = try AppSource.code("Views/Shell/ContentView/ContentView+LayoutChooser.swift")
        let body = try #require(
            source.components(separatedBy: "var workspacesMenu: some View {").dropFirst().first
        )
        #expect(body.contains("WorkspacesMenuBody(commands: windowLayoutCommands)"))
    }

    /// Neither menu builds its OWN copy of the built-in/saved/split/toolbar-buttons content any
    /// more — a regression back to two definitions would mean one of these reappears outside
    /// `WorkspacesMenuBody.swift`.
    @Test("neither menu file still declares its own workspace-content sections")
    func neitherMenuFileDeclaresItsOwnSections() throws {
        for path in [
            "App/Menus/ViewMenuPaneSections.swift",
            "Views/Shell/ContentView/ContentView+LayoutChooser.swift",
        ] {
            let source = try AppSource.code(path)
            #expect(!source.contains("var workspaceLayoutsSection"), "\(path) must not re-declare this")
            #expect(!source.contains("var savedWorkspaceSection"), "\(path) must not re-declare this")
            #expect(!source.contains("var deleteWorkspaceMenu"), "\(path) must not re-declare this")
            #expect(!source.contains("var toolbarButtonsMenu"), "\(path) must not re-declare this")
        }
    }

    // MARK: - Split's enabled rule (pure): no focus, an ordinary focused leaf, a leaf at its
    // split cap (a focused Preview leaf currently showing a workflow canvas — the one surface
    // `PaneSurface.allowsSplit` refuses, since two `WorkflowEditor`s on one binding would race).

    @Test("no focused leaf: cannot split")
    func noFocusCannotSplit() {
        #expect(!ContentView.canSplit(focusedLeafExists: false, focusedKind: nil, activeWorkflowShown: false))
        // A stale kind reading with no real leaf must not override the absence of focus.
        #expect(!ContentView.canSplit(focusedLeafExists: false, focusedKind: .preview, activeWorkflowShown: true))
    }

    @Test("an ordinary focused leaf can split")
    func ordinaryFocusedLeafCanSplit() {
        #expect(ContentView.canSplit(focusedLeafExists: true, focusedKind: .library, activeWorkflowShown: false))
        #expect(ContentView.canSplit(focusedLeafExists: true, focusedKind: .reading, activeWorkflowShown: false))
        // A focused Preview leaf that is NOT showing a workflow canvas splits normally too.
        #expect(ContentView.canSplit(focusedLeafExists: true, focusedKind: .preview, activeWorkflowShown: false))
    }

    @Test("a focused leaf at its split cap cannot split")
    func focusedLeafAtItsSplitCapCannotSplit() {
        // The one real cap in the app today: a Preview leaf showing a workflow canvas
        // (PaneSurface.workflowCanvas.allowsSplit == false) — matches the pane head's own "+"
        // refusal (previewPaneCanSplit), so the menu command agrees with it.
        #expect(!ContentView.canSplit(focusedLeafExists: true, focusedKind: .preview, activeWorkflowShown: true))
        #expect(!PaneSurface.workflowCanvas.allowsSplit)
    }

    // MARK: - WindowLayoutCommands' Equatable (pure): dampens re-render churn (same two fields →
    // equal, regardless of closure identity) while letting a REAL focus change through (either
    // field differs → not equal) — the root fix for #4968's stale-Split-state diagnosis.

    private static func commands(canSplit: Bool, kind: PaneKind?) -> WindowLayoutCommands {
        WindowLayoutCommands(
            saveWorkspace: {},
            applyWorkspace: { _ in },
            applyWorkspaceLayout: { _ in },
            splitFocusedLeaf: { _ in },
            newTab: {},
            canSplitFocusedLeaf: canSplit,
            focusedPaneKindForSplit: kind,
            isWorkspaceActive: { _ in false }
        )
    }

    @Test("two instances with the same data compare equal, even with fresh closures")
    func sameDataComparesEqualDespiteFreshClosures() {
        let a = Self.commands(canSplit: true, kind: .library)
        let b = Self.commands(canSplit: true, kind: .library)
        #expect(a == b, "an unrelated re-render must not look like a real change")
    }

    @Test("a real change in canSplitFocusedLeaf compares unequal")
    func aRealSplitEligibilityChangeComparesUnequal() {
        let a = Self.commands(canSplit: true, kind: .library)
        let b = Self.commands(canSplit: false, kind: .library)
        #expect(a != b, "canSplitFocusedLeaf flipping must republish, or the menu's enabled state goes stale")
    }

    @Test("a real change in focusedPaneKindForSplit compares unequal")
    func aRealFocusedKindChangeComparesUnequal() {
        let a = Self.commands(canSplit: true, kind: .library)
        let b = Self.commands(canSplit: true, kind: .preview)
        #expect(a != b, "the focused kind changing must republish, or a Split row names the wrong pane")
    }
}
