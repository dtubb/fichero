#if os(iOS) || os(tvOS) || os(visionOS)
import SwiftUI

/// iOS/iPadOS library switcher (#2394). Surfaces the known-library registry — the
/// same libraries the paired Mac host has — as a selectable list, and switches the
/// whole app to the chosen one. Lives in the workspace's leading toolbar so it's the
/// first thing reachable on a phone ("library list → reader → inspector").
///
/// Switching delegates to `LibraryManager.switchToRemoteLibrary(path:displayName:)`,
/// which re-roots the workspace via `currentLibraryId`. No raw networking here — the
/// registry comes from the already-shared `KnownLibraryRegistryStore`.
struct IOSLibraryPickerMenu: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var registry = KnownLibraryRegistryStore.shared

    /// Path of the currently active library, so the menu can mark it.
    private var activeLibraryPath: String? {
        guard let id = libraryManager.currentLibraryId,
              let library = libraryManager.getLibrary(id: id) else {
            return libraryManager.globalLibrary?.url.path
        }
        return library.url.path
    }

    /// Registry entries + the active library, de-duplicated by path so the
    /// currently open (possibly unregistered/paired) library always shows.
    private var entries: [(path: String, name: String)] {
        var byPath: [String: String] = [:]
        for entry in registry.libraries {
            byPath[entry.path] = entry.displayName
        }
        if let activePath = activeLibraryPath, byPath[activePath] == nil {
            let name = libraryManager.currentLibraryId
                .flatMap { libraryManager.getLibrary(id: $0)?.displayName }
                ?? URL(fileURLWithPath: activePath).deletingPathExtension().lastPathComponent
            byPath[activePath] = name
        }
        return byPath
            .map { (path: $0.key, name: $0.value) }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var body: some View {
        Menu {
            if let error = registry.fetchError {
                Text("Failed: \(error)")
                    .foregroundStyle(.secondary)
            }

            ForEach(entries, id: \.path) { entry in
                Button {
                    libraryManager.switchToRemoteLibrary(path: entry.path, displayName: entry.name)
                } label: {
                    if entry.path == activeLibraryPath {
                        Label(entry.name, systemImage: "checkmark")
                    } else {
                        Text(entry.name)
                    }
                }
            }

            if entries.isEmpty && registry.fetchError == nil {
                Text("No Libraries")
            }

            Divider()

            Button {
                Task { await registry.refresh() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
        } label: {
            Label("Libraries", systemImage: "books.vertical")
        }
        .task {
            await registry.refresh()
        }
    }
}
#endif
