import SwiftUI

@MainActor
private final class WorkflowUndoProxy {
    var apply: ((Workflow) -> Void)?

    func registerTransition(
        from currentWorkflow: Workflow,
        to targetWorkflow: Workflow,
        actionName: String,
        undoManager: UndoManager?
    ) {
        guard let undoManager else { return }
        undoManager.registerUndo(withTarget: self) { proxy in
            proxy.apply?(targetWorkflow)
            proxy.registerTransition(
                from: targetWorkflow,
                to: currentWorkflow,
                actionName: actionName,
                undoManager: undoManager
            )
        }
        undoManager.setActionName(actionName)
    }
}

/// Canvas view for workflow nodes with free placement and port-based connections
struct WorkflowCanvasView: View {
    @Binding var workflow: Workflow

    // Zoom and grid settings (controlled by parent)
    @Binding var scale: CGFloat
    @Binding var snapToGrid: Bool

    // Execution observer for node progress (uses @Observable pattern)
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    // App state for accessing AI defaults
    @Environment(AppState.self) var appState
    @Environment(\.undoManager) private var undoManager
    @EnvironmentObject var featureManager: FeatureManager

    /// Node execution states for the editor canvas.
    ///
    /// Intentionally empty (#2546 / B2): run progress now lives ONLY in the
    /// Activity monitor, so the editor stays a pure editing surface — no node
    /// progress badges, status coloring, or "∑ N files" edge labels light up
    /// during a run. Watch progress in Activity (in-sidebar or its own window).
    /// The node/edge views already render gracefully with no state.
    var nodeStates: [String: NodeExecutionState] {
        [:]
    }

    /// Live file count for a fan edge, or nil when idle. Fan-out edges
    /// read the source node's fileTotal (it's the one doing the parallel
    /// work); fan-in edges read the target node's fileTotal only if the
    /// target itself records one. Falls back to the upstream source's
    /// fileTotal so a Catalogue edge still shows "∑ 20 files" even
    /// though Catalogue itself runs once.
    func liveFanCount(for edge: WorkflowEdge, targetTool: String?) -> Int? {
        let states = nodeStates
        if let sourceState = states[edge.sourceNodeId], sourceState.fileTotal > 0 {
            return sourceState.fileTotal
        }
        if let targetState = states[edge.targetNodeId], targetState.fileTotal > 0 {
            return targetState.fileTotal
        }
        return nil
    }

    // Focus state for keyboard commands
    @FocusState private var isCanvasFocused: Bool

    // Selection state
    @State var selectedNodeIds: Set<String> = []
    @State var selectedEdgeId: String?
    @State var editingNodeId: String?

    // Edge dragging state
    @State var draggedEdge: DraggedEdge?

    // Node dragging state
    @State var nodeDragStartPosition: CGPoint?
    @State var draggingNodeIndex: Int?
    @State var dragUndoWorkflow: Workflow?
    @State private var undoProxy = WorkflowUndoProxy()

    // Node dimensions for port positioning
    let nodeWidth: CGFloat = 140
    let nodeHeight: CGFloat = 100

    // Canvas grows to fit the placed nodes (+ scroll margin), floored at a
    // comfortable minimum — large workflows no longer hit a fixed 2000×1500
    // wall (#3191). Recomputed as nodes move/add.
    private var canvasSize: CGSize {
        Self.fittedCanvasSize(
            for: workflow.nodes,
            nodeSize: CGSize(width: nodeWidth, height: nodeHeight)
        )
    }

    /// The scrollable canvas extent that contains every node plus a margin,
    /// never smaller than `minimum`. Node positions are centers, so a node's
    /// right/bottom extent is its position plus half the node size. Pure +
    /// static so it is unit-testable. (#3191)
    static func fittedCanvasSize(
        for nodes: [WorkflowNode],
        nodeSize: CGSize,
        margin: CGFloat = 400,
        minimum: CGSize = CGSize(width: 2000, height: 1500)
    ) -> CGSize {
        guard !nodes.isEmpty else { return minimum }
        let maxX = nodes.map(\.positionX).max() ?? 0
        let maxY = nodes.map(\.positionY).max() ?? 0
        return CGSize(
            width: max(minimum.width, CGFloat(maxX) + nodeSize.width / 2 + margin),
            height: max(minimum.height, CGFloat(maxY) + nodeSize.height / 2 + margin)
        )
    }

    // Pan state
    @State var offset: CGSize = .zero
    @State var lastScale: CGFloat = 1.0
    @State var lastOffset: CGSize = .zero
    @State var isPanning: Bool = false

    // Grid snapping constants
    let gridSpacing: CGFloat = 20
    let snapThreshold: CGFloat = 10

    var body: some View {
        // Outer container fills available space and clips content
        GeometryReader { _ in
            ZStack(alignment: .topLeading) {
                // Layer 1: Grid background (decorative, no interaction)
                GridPattern()
                    .stroke(Color.gray.opacity(0.2), lineWidth: 0.5)
                    .allowsHitTesting(false)

                // Layer 2: Interactive background (tap-to-deselect)
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedNodeIds.removeAll()
                        selectedEdgeId = nil
                        editingNodeId = nil
                        isCanvasFocused = true  // Re-focus for keyboard commands
                    }

                // Layer 3: Canvas content (nodes and edges)
                canvasContent
            }
            .frame(width: canvasSize.width, height: canvasSize.height)
            .scaleEffect(scale)
            .offset(offset)
            .gesture(
                MagnificationGesture()
                    .onChanged { value in
                        handleZoom(value: value)
                    }
                    .onEnded { value in
                        handleZoomEnded(value: value)
                    }
            )
            .simultaneousGesture(
                DragGesture(minimumDistance: 5)
                    .onChanged { value in
                        handlePan(value: value)
                    }
                    .onEnded { _ in
                        isPanning = false
                    }
            )
            .onDrop(of: [.plainText], isTargeted: nil) { providers, location in
                handleDrop(providers: providers, at: location)
            }
        }
        .background(Color(.textBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .focusable()
        .focused($isCanvasFocused)
        .focusEffectDisabled()
        .onAppear {
            isCanvasFocused = true
            let binding = $workflow
            undoProxy.apply = { restored in
                binding.wrappedValue = restored
            }
        }
        #if os(macOS)
        .onDeleteCommand {
            deleteSelection()
        }
        #endif
    }

    /// Delete selected edge or nodes
    private func deleteSelection() {
        let previousWorkflow = workflow

        // Delete selected edge first
        if let edgeId = selectedEdgeId {
            workflow.edges.removeAll { $0.id == edgeId }
            selectedEdgeId = nil
            registerUndo(from: previousWorkflow, actionName: "Delete Connection")
            return
        }

        // Delete selected nodes
        if !selectedNodeIds.isEmpty {
            for nodeId in selectedNodeIds {
                // Remove connected edges
                workflow.edges.removeAll { $0.sourceNodeId == nodeId || $0.targetNodeId == nodeId }
                // Remove node
                workflow.nodes.removeAll { $0.id == nodeId }
            }
            selectedNodeIds.removeAll()
            editingNodeId = nil
            registerUndo(from: previousWorkflow, actionName: "Delete Node")
        }
    }

    func registerUndo(from previousWorkflow: Workflow, actionName: String) {
        guard previousWorkflow != workflow else { return }
        undoProxy.registerTransition(
            from: workflow,
            to: previousWorkflow,
            actionName: actionName,
            undoManager: undoManager
        )
    }
}
