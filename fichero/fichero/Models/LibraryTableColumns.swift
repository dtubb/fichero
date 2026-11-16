import Foundation
import Observation
import SwiftUI

/// The item table's columns -- widths, order, shown or hidden -- remembered app-wide (#6540,
/// `library.table.columns-resize-and-remember`): every folder, every Table pane and every window, across relaunch.
/// They were kept per window (`@SceneStorage`). ONE store the tables share, written to the defaults only when the
/// columns really changed: the table hands back the same customization while it lays out (26 rounds in one session,
/// #4228), and every defaults write wakes every `@AppStorage` view in the app.
@MainActor
@Observable
final class LibraryTableColumns {
    static let shared = LibraryTableColumns()
    static let key = "library.tableColumns"

    private(set) var customization: TableColumnCustomization<LibraryOutlineNode>
    @ObservationIgnored private var saved: Data?
    @ObservationIgnored private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let data = defaults.data(forKey: Self.key)
        customization = data.flatMap(Self.decode) ?? .init()
        saved = data
    }

    /// The table's binding: the columns as the person left them.
    var binding: Binding<TableColumnCustomization<LibraryOutlineNode>> {
        Binding(get: { self.customization }, set: { self.set($0) })
    }

    /// Take the table's columns: stored and saved only when they differ from what is saved.
    func set(_ new: TableColumnCustomization<LibraryOutlineNode>) {
        guard let data = Self.encode(new), Self.changed(from: saved, to: data) else { return }
        customization = new
        saved = data
        defaults.set(data, forKey: Self.key)
    }

    nonisolated static func encode(_ customization: TableColumnCustomization<LibraryOutlineNode>) -> Data? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try? encoder.encode(customization)
    }

    nonisolated static func decode(_ data: Data) -> TableColumnCustomization<LibraryOutlineNode>? {
        try? JSONDecoder().decode(TableColumnCustomization<LibraryOutlineNode>.self, from: data)
    }

    /// Whether new columns differ from the saved ones; nothing saved yet counts as a change.
    nonisolated static func changed(from saved: Data?, to new: Data) -> Bool { saved != new }
}
