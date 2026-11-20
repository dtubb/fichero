@testable import Fichero
import Testing

/// #4880 / #6741: every pane kind renders the SAME head: a view chooser (icon,
/// label, chevron, a tick on the current view) on the left, and the kind choice in the pane
/// menu on the right (Pane >, ticked) — instead of Reader's old
/// permanently-merged single icon (`collapsesKindIntoLens`, deleted from
/// `PaneKindSelector`). The merge that remains is the shared narrowest-width
/// fallback every kind already used (`mergedRung`, unconditional now).
///
/// No `ViewInspector` or similar lives in this target (checked before
/// writing this file), so these are structural checks scoped to the exact
/// property bodies involved — the same shape `LibraryPaneHeadOwnWindowTests`
/// already uses for this reason — not a mounted render. A source scan proves
/// only that the code READS this way; it does not prove the tick or the
/// chevron actually draws. That needs a screen check.
struct PaneHeadOneChooserLadderTests {
    private static func paneKindSelectorSource() throws -> String {
        try AppSource.text("Views/Shell/PaneHead/PaneKindSelector.swift")
    }

    // MARK: - No kind merges its two controls into one any more
    // (A head PASSING `collapsesKindIntoLens` is a compile error now that the parameter is gone,
    // so no test is needed for that half.)

    @Test("PaneKindSelector no longer declares collapsesKindIntoLens or a permanent merged mode")
    func paneKindSelectorHasNoPermanentMergeSwitch() throws {
        let source = try Self.paneKindSelectorSource()
        #expect(!source.contains("var collapsesKindIntoLens"))
        #expect(!source.contains("private var mergedSelector"))
    }

    // MARK: - Every pane kind supplies currentKind, so the tick has something to compare against

    @Test("every real-leaf pane head's PaneKindSelector passes currentKind", arguments: [
        ("Views/Library/LibraryView+PaneHead.swift", "currentKind: .library"),
        ("Views/Shell/ContentView/Layout/ContentView+PreviewPaneHead.swift", "currentKind: .preview"),
        ("Views/Reader/Page/ReadingPaneView.swift", "currentKind: .reading"),
    ] as [(String, String)])
    func everyPaneHeadPassesItsOwnCurrentKind(relativePath: String, expected: String) throws {
        let source = try AppSource.text(relativePath)
        #expect(
            source.contains(expected),
            "\(relativePath) must pass \(expected) — the kind chooser's tick (#4880) has no other way to know which row is this pane's own kind."
        )
    }

    // MARK: - Both menus tick their current row, without losing the row's icon

    @Test("the selector has no kind menu: the kind choice is Pane > in the pane menu (#6741)")
    func selectorHasNoKindMenu() throws {
        let source = try Self.paneKindSelectorSource()
        #expect(!source.contains("kindControl"))
        #expect(!source.contains("kindRow"))
        #expect(!source.contains("paneKindSwitcher"))
        #expect(!source.contains("includeKindSwitcher"))
    }

    @Test("the pane head has no left close button")
    func paneHeadHasNoLeftClose() throws {
        let source = try AppSource.text("Views/Shell/PaneHead/PaneHead.swift")
        let body = try #require(
            source.components(separatedBy: "private var identityCapsule: some View {").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(!scope.contains("xmark"))
        #expect(!scope.contains("closePane"))
    }

    @Test("the sectioned view menu ticks the current lens without replacing its icon")
    func sectionedViewMenuKeepsIconAndAddsTick() throws {
        let source = try Self.paneKindSelectorSource()
        let body = try #require(
            source.components(separatedBy: "ForEach(section.1) { option in").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n                            }").first)
        #expect(scope.contains("lensRow(option)"))
        // The old code swapped the icon OUT for a bare checkmark on the selected row — #4880 asks
        // for both at once.
        #expect(!scope.contains("systemImage: \"checkmark\""))
    }
}
