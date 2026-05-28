import FicheroAPIClient
import SwiftUI

/// Main-content host for the Mind Palace sidebar mode (A1). Renders the room's
/// spatial canvas (3D via RealityKit or the 2D projection) alongside the node
/// inspector, with a toolbar carrying the room's sources (A4), the 3D/2D
/// toggle, Arrange (#1269), and Add-sources (A5). The rooms list lives in the
/// app sidebar (`RoomListView`); the two coordinate via `MindPalaceState`.
///
/// Layout uses `HStack` + `ResizableDivider` (never a nested
/// `NavigationSplitView`/`.inspector`, per `feedback_swiftui_splits`).
struct MindPalaceContainer: View {
    @ObservedObject private var state = MindPalaceState.shared

    @State private var nodes: [MindPalaceNode] = []
    @State private var connections: [MindPalaceConnection] = []
    @State private var roomName: String = ""
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var inspectorWidth: Double = 280
    @State private var showAddSources = false
    @State private var lastAIAction: String?

    private var selectedNode: MindPalaceNode? {
        guard let id = state.selectedNodeId else { return nil }
        return nodes.first { $0.id == id }
    }

    /// Distinct source documents represented in this room (A4).
    private var sourceIds: [String] {
        var seen = Set<String>()
        return nodes.compactMap { node -> String? in
            guard let sid = node.sourceId, !sid.isEmpty, seen.insert(sid).inserted else { return nil }
            return sid
        }
    }

    var body: some View {
        Group {
            if state.selectedRoomId == nil {
                ContentUnavailableView(
                    "Select a Room",
                    systemImage: "cube.transparent",
                    description: Text("Pick a room in the sidebar to view its spatial layout.")
                )
            } else {
                roomView
            }
        }
        .task(id: sceneTaskKey) { await loadScene() }
        .sheet(isPresented: $showAddSources) {
            if let roomId = state.selectedRoomId {
                AddToRoomPicker(roomId: roomId) {
                    state.reloadScene()
                }
            }
        }
    }

    /// Re-run the load task whenever the room or the revision counter changes.
    private var sceneTaskKey: String {
        "\(state.selectedRoomId ?? "none")#\(state.sceneRevision)"
    }

    private var roomView: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            HStack(spacing: 0) {
                canvas
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                ResizableDivider(
                    width: $inspectorWidth,
                    minWidth: 220,
                    maxWidth: 420,
                    edge: .trailing
                )
                SpatialNodeInspector(node: selectedNode)
                    .frame(width: inspectorWidth)
            }
            aiActivityRail
        }
    }

    // MARK: - Canvas (3D / 2D)

    @ViewBuilder
    private var canvas: some View {
        if let loadError {
            ContentUnavailableView(
                "Couldn't Load Scene",
                systemImage: "exclamationmark.triangle",
                description: Text(loadError)
            )
        } else if nodes.isEmpty && !isLoading {
            ContentUnavailableView {
                Label("Empty Room", systemImage: "circle.dashed")
            } description: {
                Text("Add sources to lay them out in this room.")
            } actions: {
                Button("Add Sources…") { showAddSources = true }
            }
        } else {
            switch state.renderMode {
            case .threeD:
                SpatialScene3D(
                    nodes: nodes,
                    connections: connections,
                    selectedNodeId: $state.selectedNodeId
                )
                // Rebuild the RealityKit scene when the room's data changes.
                .id(sceneTaskKey + "#\(nodes.count)")
            case .twoD:
                Spatial2DCanvas(
                    nodes: nodes,
                    connections: connections,
                    selectedNodeId: $state.selectedNodeId
                )
            }
        }
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack(spacing: 12) {
            Text(roomName.isEmpty ? "Room" : roomName)
                .font(.headline)
                .lineLimit(1)

            if isLoading { ProgressView().controlSize(.small) }

            sourcesMenu

            Spacer()

            arrangeMenu

            Button {
                showAddSources = true
            } label: {
                Label("Add", systemImage: "plus")
            }
            .help("Add sources to this room")

            Picker("", selection: $state.renderMode) {
                ForEach(SpatialRenderMode.allCases, id: \.self) { mode in
                    Label(mode.label, systemImage: mode.icon).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 110)
            .help("Switch between 3D and 2D")
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    /// A4 — the room's sources, derived from its nodes' `source_id`.
    private var sourcesMenu: some View {
        Menu {
            if sourceIds.isEmpty {
                Text("No source documents")
            } else {
                ForEach(sourceIds, id: \.self) { sid in
                    Button {
                        NotificationCenter.default.post(
                            name: .ficheroOpenClaimSource,
                            object: nil,
                            userInfo: ["documentId": sid]
                        )
                    } label: {
                        Label(nodeLabel(forSource: sid), systemImage: "doc.text")
                    }
                }
            }
        } label: {
            Label("Sources (\(sourceIds.count))", systemImage: "tray.full")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private var arrangeMenu: some View {
        Menu {
            Button("Semantic") { Task { await arrange(.semantic) } }
            Button("Chronological") { Task { await arrange(.chronological) } }
            Button("Thematic") { Task { await arrange(.thematic) } }
        } label: {
            Label("Arrange", systemImage: "wand.and.stars")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .disabled(nodes.isEmpty)
    }

    /// A3 stub — surfaces the most recent AI/arrangement action. The #1269 MCP
    /// server drives the same backend endpoints; this rail will stream its
    /// moves once that lands.
    @ViewBuilder
    private var aiActivityRail: some View {
        if let lastAIAction {
            Divider()
            HStack(spacing: 6) {
                Image(systemName: "sparkles").foregroundStyle(.secondary)
                Text(lastAIAction).font(.caption).foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.horizontal, 12)
            .frame(height: 28)
        }
    }

    private func nodeLabel(forSource sid: String) -> String {
        nodes.first { $0.sourceId == sid }?.displayLabel ?? sid
    }

    // MARK: - Data

    private func loadScene() async {
        guard let roomId = state.selectedRoomId, let service = activeMindPalaceService() else {
            nodes = []
            connections = []
            return
        }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            async let nodesTask = service.listNodes(roomId: roomId)
            async let connectionsTask = service.listConnections(roomId: roomId)
            async let roomsTask = service.listRooms()
            nodes = try await nodesTask
            connections = try await connectionsTask
            roomName = (try await roomsTask).first { $0.id == roomId }?.name ?? ""
        } catch {
            loadError = error.localizedDescription
            nodes = []
            connections = []
        }
    }

    private func arrange(_ type: Components.Schemas.ArrangementType) async {
        guard let roomId = state.selectedRoomId, let service = activeMindPalaceService() else { return }
        do {
            try await service.suggestArrangement(
                roomId: roomId,
                nodeIds: nodes.map(\.id),
                arrangementType: type
            )
            lastAIAction = "Arranged \(nodes.count) nodes (\(type.rawValue))"
            state.reloadScene()
        } catch {
            loadError = error.localizedDescription
        }
    }
}
