@testable import Fichero
import Testing

/// #4968: split out of `WorkspacesMenuOneDefinitionTests` (#5052) — a forbidden-pattern ABSENCE
/// guardrail, provable only by scanning the source.
struct WorkspacesMenuNoSecondDefinitionGuardrailTests {
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
}
