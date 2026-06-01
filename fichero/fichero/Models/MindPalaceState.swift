import SwiftUI

/// How the spatial canvas renders a room.
enum SpatialRenderMode: String, CaseIterable {
    case threeD = "3D"
    case twoD = "2D"

    var label: String { rawValue }
    var icon: String { self == .threeD ? "cube" : "square.grid.2x2" }
}

/// Shared, window-spanning state for the Mind Palace mode.
///
/// The sidebar (`RoomListView`) and the main content (`MindPalaceContainer`)
/// are separate SwiftUI view trees; they coordinate through this singleton —
/// which room is selected, 3D-vs-2D, the selected node, and a revision counter
/// the container watches to reload the scene after an edit/arrangement (a human
/// drag or an AI `move_node` both bump it). Mirrors the `ClaimFocusState.shared`
/// pattern already used across panes.
@MainActor
final class MindPalaceState: ObservableObject {
    static let shared = MindPalaceState()

    @Published var selectedRoomId: String?
    @Published var selectedNodeId: String?
    @Published var renderMode: SpatialRenderMode = .threeD

    /// Bumped to ask the container to re-fetch the current room's scene
    /// (after add-sources, arrangement, or any node mutation).
    @Published var sceneRevision: Int = 0

    private init() {}

    func selectRoom(_ roomId: String?) {
        guard selectedRoomId != roomId else { return }
        // Defer @Published mutations off the view-update cycle — this method is
        // called from a Binding set: closure (RoomListView roomSelection), and
        // mutating @Published state synchronously from within a view update
        // produces "Publishing changes from within view updates is not allowed"
        // runtime warnings (#1444).
        Task { @MainActor in
            self.selectedRoomId = roomId
            self.selectedNodeId = nil
        }
    }

    /// Ask the open canvas to reload the current room's nodes/connections.
    func reloadScene() {
        sceneRevision &+= 1
    }
}

/// Resolve the active library's `MindPalaceService`. Both the sidebar and the
/// canvas build their own (the wrapper is a cheap value over the shared
/// per-library API client), coordinating selection via `MindPalaceState`.
@MainActor
func activeMindPalaceService() -> MindPalaceService? {
    let manager = LibraryManager.shared
    let library = manager.currentLibraryId.flatMap { manager.getLibrary(id: $0) }
        ?? manager.openLibraries.first
        ?? manager.globalLibrary
    guard let library else { return nil }
    return MindPalaceService(ficheroClient: library.ficheroClient)
}
