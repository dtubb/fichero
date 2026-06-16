import Foundation
import SwiftUI

@MainActor
final class KnownLibraryRegistryStore: ObservableObject {
    static let shared = KnownLibraryRegistryStore()

    @Published private(set) var libraries: [KnownLibraryMenuEntry] = []

    private let apiClient = APIClient()

    private init() { }

    func refresh() async {
        do {
            let response: LibraryRegistryMenuResponse = try await apiClient.get("/registry")
            libraries = response.libraries
        } catch {
            libraries = []
        }
    }

    func noteOpenedLibrary(url: URL, displayName: String?) async {
        guard !LibraryManager.shared.isTemporaryLibrary(url) else { return }
        guard url.pathExtension.lowercased() == "fichero" else { return }

        do {
            let _: KnownLibraryMenuEntry = try await apiClient.post(
                "/registry/add",
                query: [
                    "path": url.path,
                    "name": displayName ?? url.lastPathComponent
                ]
            )
            await refresh()
        } catch {
            // Best-effort only: menu recents should never block opening/saving a library.
        }
    }

    func remove(path: String) async {
        let encodedPath = path.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? path
        do {
            try await apiClient.delete("/registry/\(encodedPath)")
            libraries.removeAll { $0.path == path }
        } catch {
            await refresh()
        }
    }

    func clearAll() async {
        let paths = libraries.map(\.path)
        for path in paths {
            await remove(path: path)
        }
    }
}

private struct LibraryRegistryMenuResponse: Decodable {
    let libraries: [KnownLibraryMenuEntry]
    let count: Int
}

struct KnownLibraryMenuEntry: Decodable, Identifiable, Equatable {
    let id: String
    let path: String
    let name: String?
    let addedAt: Date?
    let lastAccessed: Date?

    var displayName: String {
        if let trimmedName = name?.trimmingCharacters(in: .whitespacesAndNewlines),
           !trimmedName.isEmpty {
            return trimmedName
        }

        return URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
    }

    enum CodingKeys: String, CodingKey {
        case id
        case path
        case name
        case addedAt = "added_at"
        case lastAccessed = "last_accessed"
    }
}

struct FileMenuCommands: View {
    @EnvironmentObject private var libraryManager: LibraryManager
    @FocusedValue(\.openLibraryAction) private var openLibraryAction
    @FocusedValue(\.newLibraryAction) private var newLibraryAction
    @FocusedValue(\.newWindowAction) private var newWindowAction
    @FocusedValue(\.duplicateWindowAction) private var duplicateWindowAction
    @FocusedValue(\.saveLibraryAction) private var saveLibraryAction
    @FocusedValue(\.closeLibraryAction) private var closeLibraryAction
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows
    @ObservedObject private var registry = KnownLibraryRegistryStore.shared

    var body: some View {
        Group {
            Button("New Library...") {
                newLibraryAction?()
            }
            .keyboardShortcut("n", modifiers: [.command])
            .disabled(newLibraryAction == nil)

            Button("Open...") {
                openLibraryAction?()
            }
            .keyboardShortcut("o", modifiers: [.command])
            .disabled(openLibraryAction == nil)

            Menu("Open Recent") {
                if registry.libraries.isEmpty {
                    Text("No Recent Libraries")
                } else {
                    ForEach(registry.libraries) { library in
                        Button(library.displayName) {
                            openRecentLibrary(library)
                        }
                    }

                    Divider()

                    Button("Clear Menu") {
                        Task {
                            await registry.clearAll()
                        }
                    }
                }
            }
            .disabled(registry.libraries.isEmpty)

            Button("Close Database") {
                closeLibraryAction?()
            }
            .keyboardShortcut("w", modifiers: [.command, .control])
            .disabled(closeLibraryAction == nil)

            Divider()

            Button("New Window") {
                newWindowAction?()
            }
            .keyboardShortcut("t", modifiers: [.command])
            .disabled(newWindowAction == nil)

            // Duplicate Window (#2262): clones the current window's library +
            // selection + active lens into a new window via openWindow(value:).
            // Gated on supportsMultipleWindows so it disables where multiple
            // windows aren't available.
            Button("Duplicate Window") {
                duplicateWindowAction?()
            }
            .keyboardShortcut("t", modifiers: [.command, .shift])
            .disabled(duplicateWindowAction == nil || !supportsMultipleWindows)

            Divider()

            Button("Save Database As...") {
                saveLibraryAction?()
            }
            .keyboardShortcut("s", modifiers: [.command, .shift])
            .disabled(saveLibraryAction == nil)
        }
        .task {
            if registry.libraries.isEmpty {
                await registry.refresh()
            }
        }
    }

    private func openRecentLibrary(_ library: KnownLibraryMenuEntry) {
        let url = URL(fileURLWithPath: library.path)
        guard FileManager.default.fileExists(atPath: url.path) else {
            Task {
                await registry.remove(path: library.path)
            }
            return
        }

        let opened = libraryManager.openLibrary(at: url)
        libraryManager.currentLibraryId = opened.id
    }
}
