import SwiftUI

/// Hosts the Mind Palace spatial surface in its own window (opened from the
/// gated View-menu command). Resolves the active library and builds a
/// `MindPalaceService` over its API client.
///
/// Phase 1 is gated OFF by `FeatureManager.isMindPalaceEnabled`; the only
/// entry point is the gated menu command, so the window is unreachable when
/// the flag is off.
struct MindPalaceWindow: View {
    @ObservedObject private var libraryManager = LibraryManager.shared

    var body: some View {
        Group {
            if let library = activeLibrary {
                MindPalaceWindowContent(library: library)
                    .id(library.id)
            } else {
                ContentUnavailableView(
                    "No Library Open",
                    systemImage: "tray",
                    description: Text("Open a library to use the Mind Palace.")
                )
            }
        }
        .frame(minWidth: 720, minHeight: 480)
        .navigationTitle("Mind Palace")
    }

    /// Prefer the window-selected library, then any open library, then Global —
    /// mirrors the resolution order used by `LibraryWindow`.
    private var activeLibrary: LibraryManager.LibraryReference? {
        if let id = libraryManager.currentLibraryId, let library = libraryManager.getLibrary(id: id) {
            return library
        }
        return libraryManager.openLibraries.first ?? libraryManager.globalLibrary
    }
}

/// Owns the `MindPalaceService` for the resolved library. Split out so the
/// service can be a `@StateObject` seeded from the library's API client.
private struct MindPalaceWindowContent: View {
    @StateObject private var service: MindPalaceService

    init(library: LibraryManager.LibraryReference) {
        _service = StateObject(wrappedValue: MindPalaceService(ficheroClient: library.ficheroClient))
    }

    var body: some View {
        SpatialView(service: service)
    }
}
