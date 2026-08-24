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

    /// The whole policy as a table: (text editing, focused surface) → route.
    ///
    /// The second input widened from a Bool to a surface on 2026-08-23 so the
    /// inspector's lists could answer ⌘A too. Every row that existed before
    /// that is still here, unchanged in meaning: `focusedSurface: .libraryRows`
    /// is the old `libraryHasSelectableRows: true`, and nil is the old false —
    /// which keeps `.none`'s fall-through, the load-bearing case, exactly as it
    /// was.
    private struct Row {
        let rule: String
        let isTextEditing: Bool
        let focusedSurface: SelectAllSurface?
        let expected: SelectAllRoute
    }

    private static let table: [Row] = [
        Row(
            rule: "typing wins outright — ⌘A selects the text, never the library behind it",
            isTextEditing: true, focusedSurface: .libraryRows, expected: .focusedTextEditor
        ),
        Row(
            rule: "typing wins even when no library is showing",
            isTextEditing: true, focusedSurface: nil, expected: .focusedTextEditor
        ),
        Row(
            rule: "a focused library with rows selects its rows",
            isTextEditing: false, focusedSurface: .libraryRows, expected: .libraryRows
        ),
        Row(
            rule: "no text focus and no focused surface: decline, do not guess",
            isTextEditing: false, focusedSurface: nil, expected: .none
        ),
        Row(
            rule: "a focused inspector list selects its own rows",
            isTextEditing: false, focusedSurface: .inspectorList, expected: .inspectorList
        ),
        Row(
            rule: "typing inside the inspector still wins — the caret owns ⌘A",
            isTextEditing: true, focusedSurface: .inspectorList, expected: .focusedTextEditor
        ),
        Row(
            rule: "a focused sidebar selects the current library's visible rows",
            isTextEditing: false, focusedSurface: .sidebarRows, expected: .sidebarRows
        ),
        Row(
            rule: "a focused preview over an image selects the whole image",
            isTextEditing: false, focusedSurface: .previewImage, expected: .previewImage
        ),
        Row(
            rule: "renaming in the sidebar still gives ⌘A to the caret",
            isTextEditing: true, focusedSurface: .sidebarRows, expected: .focusedTextEditor
        ),
    ]

    @Test("the ⌘A routing table")
    func routingTable() {
        for row in Self.table {
            let route = SelectAllRoutingPolicy.route(
                isTextEditing: row.isTextEditing,
                focusedSurface: row.focusedSurface
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
        for surface: SelectAllSurface? in [.libraryRows, .inspectorList, .sidebarRows, .previewImage, nil] {
            #expect(
                SelectAllRoutingPolicy.route(
                    isTextEditing: true,
                    focusedSurface: surface
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
        // The reader publishes no select-all action and is not an editable
        // NSTextView, so there is no focused surface and no text focus. This is
        // the case the widening had to leave untouched: WebKit selects its own
        // text only because this route declines.
        let route = SelectAllRoutingPolicy.route(
            isTextEditing: false,
            focusedSurface: nil
        )
        #expect(route == .none)
    }

    /// An empty surface must not claim ⌘A: firing a select-all over zero rows
    /// would swallow the key equivalent and leave a focused reader or web view
    /// with nothing. A surface with nothing to select publishes nil, which is
    /// why "empty" and "not focused" are the same input.
    @Test("an empty surface declines rather than selecting nothing loudly")
    func emptySurfaceDeclines() {
        #expect(
            SelectAllRoutingPolicy.route(
                isTextEditing: false,
                focusedSurface: nil
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
