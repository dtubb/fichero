@testable import Fichero
import Foundation
import Testing

/// A folder's sort is written only when it changed: every `PaneStorage` write, even of an equal
/// value, re-evaluates every stored-setting view in the window, and this ran on every folder
/// change (`read.a-click-shows-its-folder-at-once`, #4228).
@Suite("A folder's sort is saved only when it changed")
struct LibrarySortSettingsWriteTests {

    @Test("the value the map already holds is not written again")
    func unchangedIsNotWritten() {
        #expect(LibraryView.sortJSON(#"{"a":"name","b":"date"}"#, setting: "b", to: "date") == nil)
        #expect(LibraryView.sortJSON(#"{"a":true}"#, setting: "a", to: true) == nil)
    }

    @Test("a new or changed value is written, with keys in a fixed order")
    func changedIsWrittenSorted() {
        #expect(LibraryView.sortJSON(#"{"b":"date"}"#, setting: "a", to: "name") == #"{"a":"name","b":"date"}"#)
        #expect(LibraryView.sortJSON(#"{"a":true}"#, setting: "a", to: false) == #"{"a":false}"#)
    }

    @Test("an unreadable stored map starts empty")
    func unreadableStartsEmpty() {
        #expect(LibraryView.sortJSON("not json", setting: "a", to: "name") == #"{"a":"name"}"#)
    }
}
