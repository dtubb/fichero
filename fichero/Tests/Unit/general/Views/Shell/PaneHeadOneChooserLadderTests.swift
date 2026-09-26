@testable import Fichero
import Testing

/// #4880: every pane kind renders the SAME two-control row — a kind chooser
/// (icon, chevron, a tick on the current kind) and a view chooser (icon,
/// label, chevron, a tick on the current view) — instead of Reader's old
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
    private static let realLeafPaneHeadFiles = [
        "Views/Library/LibraryView+PaneHead.swift",
        "Views/Shell/ContentView/Layout/ContentView+PreviewPaneHead.swift",
        "Views/Reader/Page/ReadingPaneView.swift",
    ]

    private static func paneKindSelectorSource() throws -> String {
        try AppSource.text("Views/Shell/PaneHead/PaneKindSelector.swift")
    }

    // MARK: - No kind merges its two controls into one any more

    @Test("no real-leaf pane head passes collapsesKindIntoLens", arguments: realLeafPaneHeadFiles)
    func noPaneHeadPassesCollapsesKindIntoLens(relativePath: String) throws {
        let source = try AppSource.text(relativePath)
        #expect(
            !source.contains("collapsesKindIntoLens"),
            "\(relativePath) still passes collapsesKindIntoLens — #4880 removed the always-merged mode so every kind renders the same two-control row."
        )
    }

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

    @Test("the kind chooser's menu rows use kindRow, which ticks the current kind without dropping its icon")
    func kindChooserRowsUseKindRow() throws {
        let source = try Self.paneKindSelectorSource()
        let body = try #require(
            source.components(separatedBy: "private var kindControl: some View {").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(scope.contains("kindRow(kind)"))
        // The old plain label lost the tick entirely; a bare `Label(kind.title,` in this scope
        // would mean the regression came back.
        #expect(!scope.contains("Label(kind.title, systemImage: kind.icon)"))
    }

    @Test("the kind chooser shows a chevron (menuIndicator is no longer forced hidden)")
    func kindChooserShowsChevron() throws {
        let source = try Self.paneKindSelectorSource()
        let body = try #require(
            source.components(separatedBy: "private var kindControl: some View {").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(
            !scope.contains(".menuIndicator(.hidden)"),
            "#4880: the kind chooser must show its chevron like every other menu; a bare icon does not read as a menu."
        )
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

    // MARK: - The narrowest fallback still folds the real kind switch in, for every kind alike

    @Test("the narrowest rung's folded-in kind switch uses kindRow too")
    func narrowestRungKindSwitchUsesKindRow() throws {
        let source = try Self.paneKindSelectorSource()
        let body = try #require(
            source.components(separatedBy: "if includeKindSwitcher, let paneKindSwitcher {").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n                    Divider()").first)
        #expect(scope.contains("kindRow(kind)"))
    }
}
