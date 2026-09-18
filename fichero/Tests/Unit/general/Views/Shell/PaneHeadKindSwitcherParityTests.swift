@testable import Fichero
import Foundation
import Testing

/// #4705: pane-head parity for the kind switcher.
///
/// `PaneKindSelector` (`Views/Shell/PaneHead/PaneKindSelector.swift`) is the
/// ONE control that lets a pane's kind be switched in place (via
/// `\.paneKindSwitcher`, injected per slot — `PaneSpec.swift`). Every pane
/// head that renders a REAL leaf kind (library/preview/reading — `.inspector`
/// and `.chat` are still placeholder leaves, `PaneSpec.swift` `kindContent`)
/// must mount it, so a user can switch ANY of those panes to any other kind
/// from the same leading control. Before this fix, the Reader head mounted
/// `PaneKindSelector<ReaderLens>` with `collapsesKindIntoLens: true`, which
/// (via `mergedRung`) skipped `kindControl` entirely — the Reader's identity
/// capsule opened only its lens menu ("Content ▾"/"Map ▾"), never a kind
/// switch, unlike Library and Preview.
struct PaneHeadKindSwitcherParityTests {

    /// The real-leaf-kind pane heads, and the file each is known to mount
    /// its `PaneKindSelector` in (`AppSource`-relative paths).
    private static let realLeafPaneHeadFiles = [
        "Views/Library/LibraryView+PaneHead.swift",
        "Views/Shell/ContentView/Layout/ContentView+PreviewPaneHead.swift",
        "Views/Reader/Page/ReadingPaneView.swift",
    ]

    @Test("every real-leaf pane head mounts PaneKindSelector", arguments: realLeafPaneHeadFiles)
    func everyRealLeafPaneHeadMountsPaneKindSelector(relativePath: String) throws {
        let root = try AppSource.root()
        let url = root.appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        #expect(
            source.contains("PaneKindSelector("),
            "\(relativePath) is a real-leaf pane head and must mount PaneKindSelector( — the kind-switcher parity #4705 requires."
        )
    }

    // MARK: - Only real kinds are offered

    @Test("selectableKinds excludes the placeholder inspector and chat leaves")
    func selectableKindsExcludesPlaceholders() {
        #expect(!PaneSpec.Kind.selectableKinds.contains(.inspector))
        #expect(!PaneSpec.Kind.selectableKinds.contains(.chat))
    }

    @Test("selectableKinds keeps every kind that renders real content")
    func selectableKindsKeepsRealKinds() {
        #expect(PaneSpec.Kind.selectableKinds.contains(.library))
        #expect(PaneSpec.Kind.selectableKinds.contains(.preview))
        #expect(PaneSpec.Kind.selectableKinds.contains(.reading))
    }

    @Test("selectableKinds is allCases minus exactly the two placeholders")
    func selectableKindsIsAllCasesMinusPlaceholders() {
        let expected = Set(PaneSpec.Kind.allCases).subtracting([.inspector, .chat])
        #expect(Set(PaneSpec.Kind.selectableKinds) == expected)
    }
}
