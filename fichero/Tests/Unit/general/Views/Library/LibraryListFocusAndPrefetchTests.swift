//
//  LibraryListFocusAndPrefetchTests.swift
//  FicheroTests
//
//  Daniel, 2026-09-02, live on 2026.09.01.2:
//   · "⌘A works in icon view but NOT in list view."
//   · "List scrolling: noticeable delay on first click of a row, then it
//      scrolls upward but barely downward."
//
//  Two root causes, both pinned here:
//   1. list mode's GUTTER tap cleared the selection without claiming pane
//      focus, so `paneFocusHint` stayed on whichever pane was clicked before
//      and ⌘A routed there. Icon mode got this fix on 2026-09-01; list mode
//      never did. The library also now answers ⌘A through the responder
//      chain, for the case where the menu key equivalent never arrives.
//   2. the scroll look-ahead's bookkeeping was `@State`, written from every
//      row's `.onAppear` — so each newly revealed row invalidated the whole
//      library body. Rows revealed by scrolling UP are already in the ledger
//      and return before the write, which is exactly the up/down asymmetry.
//

@testable import Fichero
import Foundation
import Testing

@Suite("List mode claims focus, and prefetch bookkeeping does not re-render")
struct LibraryListFocusAndPrefetchTests {

    // MARK: - ⌘A in list view

    @Test("the list gutter claims pane focus, like the icon gutter")
    func listGutterClaimsFocus() throws {
        let list = try AppSource.text("Views/Library/ViewModes/List/LibraryView+ListView.swift")
        // The claim comes FIRST and the clear still happens: a click in this
        // pane is a claim on this pane, and without it ⌘A keeps routing to
        // whatever was focused before.
        #expect(
            list.contains("onRequestFocus()\n                apply(SelectionGrammar.clear())"),
            """
            the list's empty-space tap must call `onRequestFocus()` immediately \
            before it clears the selection.
            """
        )
    }

    @Test("icon and list gutters make the same claim")
    func bothGuttersAgree() throws {
        let icon = try AppSource.text("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift")
        #expect(icon.contains("onRequestFocus()"),
                "scan read the wrong file — icon mode is the reference for this fix")
    }

    @Test("the library answers ⌘A through the responder chain too")
    func libraryHandlesCommandAInTheResponderChain() throws {
        let keys = try AppSource.text("Views/Library/LibraryView+KeyboardShortcuts.swift")
        #expect(keys.contains(".onKeyPress(keys: [\"a\"], phases: .down)"))
        #expect(keys.contains("keyPress.modifiers == .command"),
                "a BARE `a` is type-to-select; only the ⌘ chord may select all")
        #expect(keys.contains("guard !selectAllIds.isEmpty else { return .ignored }"),
                "an empty surface must decline so ⌘A falls through, matching "
                    + "SelectAllRoute.none")
        #expect(keys.contains("guard !isTextEntryActive"),
                "⌘A must yield to a live rename / filter / search field")
    }

    @Test("this is NOT a second ⌘A menu key equivalent")
    func noSecondMenuKeyEquivalent() throws {
        // `MenuShortcutBoundaryTests` owns the app-wide rule; this guard states
        // the library lane's half of it, so a future edit here cannot quietly
        // grow a `.keyboardShortcut` and reopen #4376.
        let keys = try AppSource.text("Views/Library/LibraryView+KeyboardShortcuts.swift")
        #expect(!keys.contains("keyboardShortcut(\"a\""))
        #expect(!keys.contains("keyboardShortcut(\"A\""))
    }

    // MARK: - Prefetch bookkeeping must not invalidate the view

    @Test("the prefetch ledger is held by reference, not as @State")
    func prefetchLedgerIsAReference() throws {
        let view = try AppSource.text("Views/Library/LibraryView.swift")
        #expect(view.contains("@State var thumbnailPrefetch = ThumbnailPrefetchLedger()"))
        for gone in ["prefetchedThumbnailIds", "thumbnailPrefetchTask", "folderThumbnailPrefetchTask"] {
            #expect(!view.contains("@State var \(gone)"),
                    "`\(gone)` is written from a row's .onAppear; as @State that is one "
                        + "whole-library re-render per revealed row")
        }
    }

    @Test("the ledger is deliberately not @Observable")
    func ledgerIsNotObservable() throws {
        let ledger = try AppSource.text("Views/Library/ThumbnailPrefetchLedger.swift")
        #expect(ledger.contains("final class ThumbnailPrefetchLedger"))
        #expect(!ledger.contains("@Observable"),
                "observing it would restore exactly the per-row invalidation this "
                    + "type exists to remove")
    }

    @Test("one claim seam, so the folder sweep and the look-ahead cannot double-fetch")
    func oneClaimSeam() throws {
        let icon = try AppSource.text("Views/Library/ViewModes/Icon/LibraryView+IconMode.swift")
        #expect(icon.components(separatedBy: "thumbnailPrefetch.claimUnfetched(").count - 1 == 2,
                "both the folder sweep and the scroll look-ahead claim through the ledger")
        #expect(!icon.contains("prefetchedThumbnailIds"),
                "no call site may keep its own copy of the ledger's set")
    }

    @Test("the ledger claims each id exactly once")
    @MainActor
    func claimUnfetchedIsIdempotent() {
        let ledger = ThumbnailPrefetchLedger()
        #expect(ledger.claimUnfetched(["a", "b", "c"]) == ["a", "b", "c"])
        // The overlapping window a scrolling look-ahead produces: only the new
        // ids come back, which is what makes an upward scroll write nothing.
        #expect(ledger.claimUnfetched(["b", "c", "d"]) == ["d"])
        #expect(ledger.claimUnfetched(["a", "b"]).isEmpty)

        ledger.resetScrollLookAhead()
        #expect(ledger.claimUnfetched(["a"]) == ["a"], "a new document set re-fetches")
    }
}
