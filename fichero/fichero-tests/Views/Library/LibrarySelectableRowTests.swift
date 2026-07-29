@testable import Fichero
import SwiftUI
import Testing

/// #3868 — the list-row selection tint is diffed by VALUE so one selection click
/// only re-renders the rows whose selection actually changed. These lock the
/// `Equatable` contract SwiftUI's `.equatable()` relies on: equal (skippable) when
/// identity + isSelected + tint match, regardless of content; unequal when any of
/// those change.
@MainActor
struct LibrarySelectableRowTests {

    @Test("Same identity/isSelected/tint are equal even with different content (row is skipped)")
    func equalIgnoresContent() {
        let base = LibrarySelectableRow(identity: "doc1", isSelected: false, tint: Color.accentColor) {
            Text("A")
        }
        let differentContent = LibrarySelectableRow(identity: "doc1", isSelected: false, tint: Color.accentColor) {
            Text("B")
        }
        #expect(base == differentContent)
    }

    @Test("A flipped selection is not equal — the row must re-render")
    func selectionFlipBreaksEquality() {
        let unselected = LibrarySelectableRow(identity: "doc1", isSelected: false, tint: Color.accentColor) {
            Text("A")
        }
        let selected = LibrarySelectableRow(identity: "doc1", isSelected: true, tint: Color.accentColor) {
            Text("A")
        }
        #expect(unselected != selected)
    }

    @Test("A different data identity is not equal")
    func identityBreaksEquality() {
        let first = LibrarySelectableRow(identity: "doc1", isSelected: false, tint: Color.accentColor) {
            Text("A")
        }
        let second = LibrarySelectableRow(identity: "doc2", isSelected: false, tint: Color.accentColor) {
            Text("A")
        }
        #expect(first != second)
    }

    @Test("A different tint (e.g. pane focus changed) is not equal")
    func tintBreaksEquality() {
        let accent = LibrarySelectableRow(identity: "doc1", isSelected: true, tint: Color.accentColor) {
            Text("A")
        }
        let secondary = LibrarySelectableRow(identity: "doc1", isSelected: true, tint: Color.secondary) {
            Text("A")
        }
        #expect(accent != secondary)
    }
}
