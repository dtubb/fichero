@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// The item table's columns are remembered app-wide (#6540, `library.table.columns-resize-and-remember`), and written
/// only when they change (#4228: the table hands the same columns back while it lays out).
@MainActor
struct LibraryTableColumnsTests {
    private func scratch() throws -> UserDefaults {
        let name = "LibraryTableColumnsTests-\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: name))
        defaults.removePersistentDomain(forName: name)
        return defaults
    }

    @Test("the same columns handed back write nothing; changed ones are saved and read by a new store")
    func savedOnlyWhenChanged() throws {
        let defaults = try scratch()
        let store = LibraryTableColumns(defaults: defaults)
        let blank = store.customization
        store.set(blank)
        let first = defaults.data(forKey: LibraryTableColumns.key)
        #expect(first != nil, "nothing saved yet counts as a change")
        store.set(blank)
        #expect(defaults.data(forKey: LibraryTableColumns.key) == first)

        var hidden = blank
        hidden[visibility: "kind"] = .hidden
        store.set(hidden)
        #expect(defaults.data(forKey: LibraryTableColumns.key) != first)
        // Another window, or the next launch, reads the same columns.
        #expect(LibraryTableColumns(defaults: defaults).customization[visibility: "kind"] == .hidden)
    }

    @Test("the comparison is of the saved bytes")
    func changedCompares() {
        #expect(LibraryTableColumns.changed(from: nil, to: Data([1])))
        #expect(!LibraryTableColumns.changed(from: Data([1]), to: Data([1])))
        #expect(LibraryTableColumns.changed(from: Data([1]), to: Data([2])))
    }
}
