import SwiftUI

/// Read-only 2D projection of a Mind Palace room (Phase 1).
///
/// Renders each `MindPalaceNode` at its **backend-provided** `positionX`/
/// `positionY`, draws `MindPalaceConnection` edges between them, and labels
/// nodes by kind. The only client-side transform is a fit-to-view camera
/// (uniform translate + scale of the whole scene so it's on-screen) — relative
/// node geometry is never recomputed here. Layout, arrangement, and dedup are
/// backend concerns (`feedback_kg_logic_in_backend`).
///
/// Editing — drag-to-reposition (`move_node`) and viewport persistence
/// (`save_viewport`) — is Phase 2. This surface is intentionally view-only.
struct SpatialView: View {
    @ObservedObject var service: MindPalaceService

    @State private var rooms: [MindPalaceRoom] = []
    @State private var selectedRoomId: String?
    @State private var nodes: [MindPalaceNode] = []
    @State private var connections: [MindPalaceConnection] = []
    @State private var isLoadingRooms = false
    @State private var isLoadingScene = false
    @State private var loadError: String?

    @State private var roomListWidth: Double = 220

    var body: some View {
        HStack(spacing: 0) {
            roomList
                .frame(width: roomListWidth)

            ResizableDivider(
                width: $roomListWidth,
                minWidth: 160,
                maxWidth: 360,
                edge: .leading
            )

            canvasPane
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task { await loadRooms() }
    }

    // MARK: - Room list (left pane)

    private var roomList: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Rooms")
                    .font(.headline)
                    .foregroundStyle(.primary)
                Spacer()
                if isLoadingRooms {
                    ProgressView().controlSize(.small)
                }
            }
            .padding(.horizontal, 12)
            .frame(height: 44)

            Divider()

            if rooms.isEmpty && !isLoadingRooms {
                ContentUnavailableView(
                    "No Rooms",
                    systemImage: "square.on.square.dashed",
                    description: Text("This library has no Mind Palace rooms yet.")
                )
            } else {
                List(rooms, selection: $selectedRoomId) { room in
                    Label(room.name, systemImage: "square.stack.3d.up")
                        .tag(room.id)
                }
                .listStyle(.sidebar)
            }
        }
        .background(.bar)
        .onChange(of: selectedRoomId) { _, newValue in
            guard let roomId = newValue else { return }
            Task { await loadScene(roomId: roomId) }
        }
    }

    // MARK: - Canvas (right pane)

    @ViewBuilder
    private var canvasPane: some View {
        VStack(spacing: 0) {
            canvasHeader
            Divider()

            if let loadError {
                ContentUnavailableView(
                    "Couldn't Load Scene",
                    systemImage: "exclamationmark.triangle",
                    description: Text(loadError)
                )
            } else if selectedRoomId == nil {
                ContentUnavailableView(
                    "Select a Room",
                    systemImage: "square.stack.3d.up",
                    description: Text("Pick a room to view its spatial layout.")
                )
            } else if nodes.isEmpty && !isLoadingScene {
                ContentUnavailableView(
                    "Empty Room",
                    systemImage: "circle.dashed",
                    description: Text("This room has no placed nodes yet.")
                )
            } else {
                SpatialCanvas(nodes: nodes, connections: connections)
            }
        }
    }

    private var canvasHeader: some View {
        HStack(spacing: 12) {
            if isLoadingScene {
                ProgressView().controlSize(.small)
            }
            if !nodes.isEmpty {
                Text("\(nodes.count) nodes · \(connections.count) connections")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            nodeTypeLegend
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    private var nodeTypeLegend: some View {
        HStack(spacing: 10) {
            ForEach(MindPalaceNodeType.allCases.filter { $0 != .unknown }, id: \.self) { type in
                HStack(spacing: 4) {
                    Circle().fill(type.color).frame(width: 8, height: 8)
                    Text(type.label).font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - Loading

    private func loadRooms() async {
        isLoadingRooms = true
        loadError = nil
        defer { isLoadingRooms = false }
        do {
            rooms = try await service.listRooms()
            if selectedRoomId == nil, let first = rooms.first {
                selectedRoomId = first.id
            }
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func loadScene(roomId: String) async {
        isLoadingScene = true
        loadError = nil
        defer { isLoadingScene = false }
        do {
            async let nodesTask = service.listNodes(roomId: roomId)
            async let connectionsTask = service.listConnections(roomId: roomId)
            nodes = try await nodesTask
            connections = try await connectionsTask
        } catch {
            loadError = error.localizedDescription
            nodes = []
            connections = []
        }
    }
}

/// The fit-to-view scatter canvas. Pure render of backend coordinates.
private struct SpatialCanvas: View {
    let nodes: [MindPalaceNode]
    let connections: [MindPalaceConnection]

    private let nodeDiameter: CGFloat = 14
    private let padding: CGFloat = 48

    var body: some View {
        GeometryReader { geo in
            let layout = projectedPositions(in: geo.size)
            ZStack {
                // Edges drawn beneath nodes.
                Canvas { context, _ in
                    for connection in connections {
                        guard
                            let fromPoint = layout[connection.sourceNodeId],
                            let toPoint = layout[connection.targetNodeId]
                        else { continue }
                        var path = Path()
                        path.move(to: fromPoint)
                        path.addLine(to: toPoint)
                        context.stroke(
                            path,
                            with: .color(connection.connectionType.color.opacity(0.5)),
                            lineWidth: 1.5
                        )
                    }
                }

                // Node chips at projected positions.
                ForEach(nodes) { node in
                    if let point = layout[node.id] {
                        nodeChip(node).position(point)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .textBackgroundColor))
        }
    }

    private func nodeChip(_ node: MindPalaceNode) -> some View {
        HStack(spacing: 5) {
            Image(systemName: node.nodeType.icon)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: nodeDiameter, height: nodeDiameter)
                .background(node.nodeType.color, in: Circle())
            Text(node.displayLabel)
                .font(.caption)
                .lineLimit(1)
                .foregroundStyle(.primary)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(.regularMaterial, in: Capsule())
        .overlay(Capsule().stroke(node.nodeType.color.opacity(0.4), lineWidth: 1))
        .help("\(node.nodeType.label): \(node.displayLabel)")
    }

    /// Map backend (x, y) coordinates into view space with a uniform
    /// fit-to-view transform. Y is flipped so positive-y reads as "up".
    /// This frames the scene without altering relative node geometry.
    private func projectedPositions(in size: CGSize) -> [String: CGPoint] {
        guard !nodes.isEmpty else { return [:] }

        let xValues = nodes.map(\.positionX)
        let yValues = nodes.map(\.positionY)
        let minX = xValues.min() ?? 0
        let maxX = xValues.max() ?? 0
        let minY = yValues.min() ?? 0
        let maxY = yValues.max() ?? 0

        let spanX = maxX - minX
        let spanY = maxY - minY

        let availableW = Double(size.width) - Double(padding) * 2
        let availableH = Double(size.height) - Double(padding) * 2

        // Uniform scale that fits the wider of the two spans; if a span is
        // zero (all nodes share a coordinate) we don't scale that axis.
        let scaleX = spanX > 0 ? availableW / spanX : 1
        let scaleY = spanY > 0 ? availableH / spanY : 1
        let scale = min(scaleX, scaleY)

        let contentW = spanX * scale
        let contentH = spanY * scale
        let offsetX = (Double(size.width) - contentW) / 2
        let offsetY = (Double(size.height) - contentH) / 2

        var result: [String: CGPoint] = [:]
        for node in nodes {
            let pointX = offsetX + (node.positionX - minX) * scale
            // Flip Y: larger backend y → higher on screen (smaller view y).
            let pointY = offsetY + (maxY - node.positionY) * scale
            result[node.id] = CGPoint(x: pointX, y: pointY)
        }
        return result
    }
}
