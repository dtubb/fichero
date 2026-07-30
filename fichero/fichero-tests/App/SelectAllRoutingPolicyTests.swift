@testable import Fichero
import Foundation
import Testing

/// #4376: ⌘A must act on the FOCUSED surface, like every Mac app.
///
/// Same root cause as #4354's ⌘Z: a `.keyboardShortcut` on a menu item becomes
/// an NSMenuItem key equivalent, and AppKit matches key equivalents BEFORE the
/// responder chain. A command claimed once at app level therefore reaches past
/// whatever the user is actually looking at.
///
/// The library half of this bug was the opposite failure — nothing claimed ⌘A
/// at all, the published `librarySelectAll` action had no consumer, and the
/// system Select All walked a responder chain whose `ScrollView`+`LazyVStack`
/// implements no `selectAll(_:)`. Nothing happened.
struct SelectAllRoutingPolicyTests {

    /// The whole policy as a table: (text editing, library has rows) → route.
    private struct Row {
        let rule: String
        let isTextEditing: Bool
        let libraryHasSelectableRows: Bool
        let expected: SelectAllRoute
    }

    private static let table: [Row] = [
        Row(
            rule: "typing wins outright — ⌘A selects the text, never the library behind it",
            isTextEditing: true, libraryHasSelectableRows: true, expected: .focusedTextEditor
        ),
        Row(
            rule: "typing wins even when no library is showing",
            isTextEditing: true, libraryHasSelectableRows: false, expected: .focusedTextEditor
        ),
        Row(
            rule: "a focused library with rows selects its rows",
            isTextEditing: false, libraryHasSelectableRows: true, expected: .libraryRows
        ),
        Row(
            rule: "no text focus and no focused library rows: decline, do not guess",
            isTextEditing: false, libraryHasSelectableRows: false, expected: .none
        ),
    ]

    @Test("the ⌘A routing table")
    func routingTable() {
        for row in Self.table {
            let route = SelectAllRoutingPolicy.route(
                isTextEditing: row.isTextEditing,
                libraryHasSelectableRows: row.libraryHasSelectableRows
            )
            #expect(route == row.expected, Comment(rawValue: row.rule))
        }
    }

    /// Text focus is absolute. This is the assertion that stops someone
    /// "helpfully" falling through to the library when the caret's own
    /// select-all looks like a no-op — the exact mistake #4354 documents for
    /// an empty typing undo stack.
    @Test("a focused text editor is never overridden by the library")
    func textEditingIsNeverOverridden() {
        for libraryHasRows in [true, false] {
            #expect(
                SelectAllRoutingPolicy.route(
                    isTextEditing: true,
                    libraryHasSelectableRows: libraryHasRows
                ) == .focusedTextEditor
            )
        }
    }

    /// The reader is a WebKit surface: selecting its text is the web view's own
    /// job. The app must DISABLE its item so the key equivalent falls through
    /// to the system Select All and on down the responder chain. `.none` is the
    /// route that expresses "not ours" — it is a decision, not a failure.
    @Test("a focused reader routes to none so WebKit keeps its own select-all")
    func readerFallsThrough() {
        // The reader publishes no library select-all action and is not an
        // editable NSTextView, so both inputs are false.
        let route = SelectAllRoutingPolicy.route(
            isTextEditing: false,
            libraryHasSelectableRows: false
        )
        #expect(route == .none)
    }

    /// An empty library must not claim ⌘A: firing a select-all over zero rows
    /// would swallow the key equivalent and leave a focused reader or web view
    /// with nothing.
    @Test("an empty library declines rather than selecting nothing loudly")
    func emptyLibraryDeclines() {
        #expect(
            SelectAllRoutingPolicy.route(
                isTextEditing: false,
                libraryHasSelectableRows: false
            ) == .none
        )
    }

    // MARK: - The #4376 ↔ #4377 interaction

    /// ⌘A has to leave a usable anchor behind, or the following ⇧-click
    /// extends from a row the user can no longer see.
    @Test("select all leaves an anchor a following shift-click can narrow from")
    func selectAllLeavesAUsableAnchor() {
        let ids = ["a", "b", "c", "d"]
        let all = SelectionGrammar.selectAll(in: ids)
        #expect(all.selection == Set(ids))
        #expect(all.anchor == "a")

        let narrowed = SelectionGrammar.click(
            id: "b",
            in: ids,
            selection: all.selection,
            anchor: all.anchor,
            modifiers: [.shift]
        )
        #expect(narrowed.selection == ["a", "b"])
    }
}
