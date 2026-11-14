@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/panes-workspaces.md -- `panes.focus.any-pane-fills-the-screen` and
/// `panes.focus.esc-restores-exactly` (#6575). ⌃⌘R focuses the focused pane, any kind; a Preview showing a page keeps
/// the page reader; Focus shows the one pane and never changes the stored list. What breaks without these: a chord that
/// only works on a page, or a Focus that leaves the workspace with one pane in it.
@MainActor
struct PaneFocusTests {
    private let source = UUID(), reader = UUID(), segments = UUID(), split = UUID()

    private var list: PaneList {
        PaneList([
            .leaf(id: source, kind: .preview, scope: .current, config: .none),
            .split(id: split, axis: .vertical, children: [
                .leaf(id: reader, kind: .reading, scope: .current, config: .none),
                .leaf(id: segments, kind: .segments, scope: .current, config: .none)
            ])
        ])
    }

    @Test("Focus shows the one pane, nested or not, and the stored list is unchanged")
    func showsOnePane() {
        let stored = list
        let focused = stored.focusing(segments)
        #expect(focused.leafCount == 1)
        #expect(focused.leafIDs(of: .segments) == [segments])
        #expect(stored == list, "Focus is a view of the list, never a change to it")
        #expect(stored.focusing(UUID()) == stored, "a pane that is gone focuses nothing")
    }

    @Test("⌃⌘R focuses Reader and Segments panes; on a Preview showing a page it opens the page reader; again it leaves")
    func theChord() {
        #expect(FocusMode.step(focusedNow: nil, focusedKind: .reading, focusedLeaf: reader, hasPage: true) == .focus(reader))
        #expect(FocusMode.step(focusedNow: nil, focusedKind: .segments, focusedLeaf: segments, hasPage: false) == .focus(segments))
        #expect(FocusMode.step(focusedNow: nil, focusedKind: .preview, focusedLeaf: source, hasPage: true) == .readPage)
        #expect(FocusMode.step(focusedNow: nil, focusedKind: .preview, focusedLeaf: source, hasPage: false) == .focus(source),
                "a Source showing a folder is focused as a pane")
        #expect(FocusMode.step(focusedNow: nil, focusedKind: nil, focusedLeaf: nil, hasPage: true) == .readPage)
        #expect(FocusMode.step(focusedNow: nil, focusedKind: nil, focusedLeaf: nil, hasPage: false) == .nothing)
        #expect(FocusMode.step(focusedNow: reader, focusedKind: .reading, focusedLeaf: reader, hasPage: true) == .leave)
    }
}
