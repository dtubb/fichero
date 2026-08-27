@testable import Fichero
import Foundation
import Testing

// MARK: - KnownLibraryMenuEntry display-name tests

@Suite("KnownLibraryMenuEntry list→row mapping")
struct KnownLibraryMenuEntryTests {
    private func makeEntry(id: String = "a1", path: String, name: String?) -> KnownLibraryMenuEntry {
        KnownLibraryMenuEntry(id: id, path: path, name: name, addedAt: nil, lastAccessed: nil)
    }

    @Test("Uses name when present and non-empty")
    func usesNameWhenPresent() {
        let entry = makeEntry(path: "/Libs/My Library.fichero", name: "My Library")
        #expect(entry.displayName == "My Library")
    }

    @Test("Trims whitespace from name")
    func trimsName() {
        let entry = makeEntry(path: "/Libs/My Library.fichero", name: "  My Library  ")
        #expect(entry.displayName == "My Library")
    }

    @Test("Falls back to filename stem when name is nil")
    func fallsBackToFilenameStemWhenNil() {
        let entry = makeEntry(path: "/Libs/Work Archive.fichero", name: nil)
        #expect(entry.displayName == "Work Archive")
    }

    @Test("Falls back to filename stem when name is empty string")
    func fallsBackToFilenameStemWhenEmpty() {
        let entry = makeEntry(path: "/Libs/Work Archive.fichero", name: "")
        #expect(entry.displayName == "Work Archive")
    }

    @Test("Falls back to filename stem when name is all whitespace")
    func fallsBackToFilenameStemWhenWhitespace() {
        let entry = makeEntry(path: "/Libs/Research.fichero", name: "   ")
        #expect(entry.displayName == "Research")
    }
}

// MARK: - Picker entries helper (mirrors IOSLibraryPickerMenu.entries)

/// Extracted copy of `IOSLibraryPickerMenu.entries` logic for unit-testing
/// without needing to instantiate the private SwiftUI view.
private func pickerEntries(
    from libraries: [KnownLibraryMenuEntry],
    activePath: String?
) -> [(path: String, name: String)] {
    var byPath: [String: String] = [:]
    for lib in libraries { byPath[lib.path] = lib.displayName }
    if let active = activePath, byPath[active] == nil {
        byPath[active] = URL(fileURLWithPath: active).deletingPathExtension().lastPathComponent
    }
    return byPath.map { (path: $0.key, name: $0.value) }
        .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
}

@Suite("iOS library picker entries computation")
struct IOSLibraryPickerMenuTests {
    private func makeLib(_ path: String, name: String? = nil) -> KnownLibraryMenuEntry {
        KnownLibraryMenuEntry(id: path, path: path, name: name, addedAt: nil, lastAccessed: nil)
    }

    @Test("All registry entries appear as rows, sorted by name")
    func allEntriesAppear() {
        let libs = [
            makeLib("/Libs/Zebra.fichero", name: "Zebra"),
            makeLib("/Libs/Alpha.fichero", name: "Alpha")
        ]
        let entries = pickerEntries(from: libs, activePath: nil)
        #expect(entries.map(\.name) == ["Alpha", "Zebra"])
    }

    @Test("Active library is included even when absent from registry")
    func activeLibraryAddedWhenMissing() {
        let libs = [makeLib("/Libs/Alpha.fichero", name: "Alpha")]
        let entries = pickerEntries(from: libs, activePath: "/Libs/Beta.fichero")
        #expect(entries.count == 2)
        #expect(entries.map(\.path).contains("/Libs/Beta.fichero"))
    }

    @Test("Active library is not duplicated when already in registry")
    func activeLibraryNotDuplicated() {
        let libs = [makeLib("/Libs/Alpha.fichero", name: "Alpha")]
        let entries = pickerEntries(from: libs, activePath: "/Libs/Alpha.fichero")
        #expect(entries.count == 1)
    }

    @Test("Empty registry with no active path returns empty list")
    func emptyRegistryEmptyActiveReturnsEmpty() {
        let entries = pickerEntries(from: [], activePath: nil)
        #expect(entries.isEmpty)
    }

    @Test("Empty registry with active path returns single active entry")
    func emptyRegistryWithActivePathReturnsSingleEntry() {
        let entries = pickerEntries(from: [], activePath: "/Libs/global.fichero")
        #expect(entries.count == 1)
        #expect(entries.first?.path == "/Libs/global.fichero")
        #expect(entries.first?.name == "global")
    }
}

// MARK: - KnownLibraryRegistryStore published surface

@Suite("KnownLibraryRegistryStore published surface")
struct KnownLibraryRegistryStoreTests {
    @Test("fetchError property is accessible (not compile error)")
    @MainActor
    func fetchErrorAccessible() {
        let store = KnownLibraryRegistryStore.shared
        _ = store.fetchError  // must compile; value depends on network state
    }

    @Test("libraries property is accessible (not compile error)")
    @MainActor
    func librariesAccessible() {
        let store = KnownLibraryRegistryStore.shared
        _ = store.libraries
    }
}
