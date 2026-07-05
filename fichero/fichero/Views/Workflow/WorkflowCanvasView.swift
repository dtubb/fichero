// swiftlint:disable file_length
import SwiftUI

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

    /// Node execution states for the editor canvas.
    ///
    /// Intentionally empty (#2546 / B2): run progress now lives ONLY in the
    /// Activity monitor, so the editor stays a pure editing surface — no node
    /// progress badges, status coloring, or "∑ N files" edge labels light up
    /// during a run. Watch progress in Activity (in-sidebar or its own window).
    /// The node/edge views already render gracefully with no state.
    private var nodeStates: [String: NodeExecutionState] {
        [:]
    }

    /// Live file count for a fan edge, or nil when idle. Fan-out edges
    /// read the source node's fileTotal (it's the one doing the parallel
    /// work); fan-in edges read the target node's fileTotal only if the
    /// target itself records one. Falls back to the upstream source's
    /// fileTotal so a Catalogue edge still shows "∑ 20 files" even
    /// though Catalogue itself runs once.
    fileprivate func liveFanCount(for edge: WorkflowEdge, targetTool: String?) -> Int? {
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

    // Node dimensions for port positioning
    let nodeWidth: CGFloat = 140
    let nodeHeight: CGFloat = 100

    // Canvas size (large enough to scroll around)
    private let canvasSize: CGSize = CGSize(width: 2000, height: 1500)

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
        .onAppear { isCanvasFocused = true }
        #if os(macOS)
        .onDeleteCommand {
            deleteSelection()
        }
        #endif
    }

    /// Delete selected edge or nodes
    private func deleteSelection() {
        // Delete selected edge first
        if let edgeId = selectedEdgeId {
            workflow.edges.removeAll { $0.id == edgeId }
            selectedEdgeId = nil
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
        }
    }
}

// MARK: - Canvas Content

extension WorkflowCanvasView {
    @ViewBuilder
    var canvasContent: some View {
        ZStack {
            // Edges layer (behind nodes)
            edgesLayer

            // Edge being dragged
            if let dragged = draggedEdge {
                DraggingWorkflowEdgeView(startPoint: dragged.startPoint, currentPoint: dragged.currentPoint)
            }

            // Nodes layer
            nodesLayer
        }
    }
}

// MARK: - Edges Layer

extension WorkflowCanvasView {
    @ViewBuilder
    var edgesLayer: some View {
        let portPositions = calculatePortPositions()

        ForEach(workflow.edges) { edge in
            if let sourcePoint = portPositions["\(edge.sourceNodeId):\(edge.sourcePortId)"],
               let targetPoint = portPositions["\(edge.targetNodeId):\(edge.targetPortId)"] {
                let sourceTool = workflow.nodes.first { $0.id == edge.sourceNodeId }?.tool
                let targetTool = workflow.nodes.first { $0.id == edge.targetNodeId }?.tool
                WorkflowEdgeView(
                    edge: edge,
                    sourcePoint: sourcePoint,
                    targetPoint: targetPoint,
                    isSelected: edge.id == selectedEdgeId,
                    isConditional: edge.condition != nil,
                    fanRole: EdgeFanRoleResolver.role(
                        sourceTool: sourceTool,
                        targetTool: targetTool
                    ),
                    fanCount: liveFanCount(for: edge, targetTool: targetTool)
                )
                .onTapGesture {
                    selectedNodeIds.removeAll()
                    editingNodeId = nil
                    selectedEdgeId = edge.id
                    isCanvasFocused = true  // Re-focus for keyboard commands
                }
                .contextMenu {
                    Button(role: .destructive) {
                        workflow.edges.removeAll { $0.id == edge.id }
                        selectedEdgeId = nil
                    } label: {
                        Label("Delete Connection", systemImage: "trash")
                    }
                }
            }
        }
    }
}

// MARK: - Nodes Layer

extension WorkflowCanvasView {
    @ViewBuilder
    var nodesLayer: some View {
        ForEach(Array(workflow.nodes.enumerated()), id: \.element.id) { index, node in
            nodeView(for: node, at: index)
        }
    }

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    private func nodeView(for node: WorkflowNode, at index: Int) -> some View {
        // Container with explicit frame for proper popover anchoring
        WorkflowNodeView(
            node: node,
            isSelected: selectedNodeIds.contains(node.id),
            connectedInputPorts: connectedInputPorts(for: node.id),
            connectedOutputPorts: connectedOutputPorts(for: node.id),
            canAcceptDrop: draggedEdge != nil && draggedEdge?.sourceNodeId != node.id,
            onPortDragStarted: { port, _ in
                startEdgeDrag(from: node, port: port)
            },
            onPortDragChanged: { translation in
                updateEdgeDrag(translation: translation)
            },
            onPortDragEnded: {
                endEdgeDrag()
            },
            onPortDropReceived: { port, _ in
                completeEdge(to: node, port: port)
            },
            onInputPortDetach: { port, nodeId in
                detachAndRedrag(fromNode: nodeId, port: port)
            },
            executionState: nodeStates[node.id]
        )
        .frame(width: nodeWidth, height: nodeHeight)
        .popover(
            isPresented: Binding(
                get: { editingNodeId == node.id },
                set: { if !$0 { editingNodeId = nil } }
            ),
            attachmentAnchor: .rect(.bounds),
            arrowEdge: .top
        ) {
            NodePopover(
                node: Binding(
                    get: { workflow.nodes[index] },
                    set: { workflow.nodes[index] = $0 }
                ),
                allNodes: workflow.nodes,
                workflowId: workflow.id,
                onDelete: {
                    deleteNode(at: index)
                },
                onDuplicate: {
                    duplicateNode(at: index)
                }
            )
            .environment(executionObserver)
        }
        .position(x: node.positionX, y: node.positionY)
        // Double tap to open popover for editing (must come before single tap)
        .onTapGesture(count: 2) {
            selectedEdgeId = nil
            selectedNodeIds = [node.id]
            editingNodeId = node.id
        }
        // Single tap to select (allows delete key to work)
        .onTapGesture {
            selectedEdgeId = nil
            selectedNodeIds = [node.id]
            editingNodeId = nil  // Close any open popover
            isCanvasFocused = true  // Keep focus on canvas for keyboard commands
        }
        // Drag to move node - use regular gesture so port's highPriorityGesture takes precedence
        .gesture(
            DragGesture(minimumDistance: 3)
                .onChanged { value in
                    handleNodeDrag(value: value, index: index)
                }
                .onEnded { _ in
                    nodeDragStartPosition = nil
                    draggingNodeIndex = nil
                }
        )
        // Context menu for node
        .contextMenu {
            Button {
                editingNodeId = node.id
            } label: {
                Label("Edit", systemImage: "pencil")
            }

            Button {
                duplicateNode(at: index)
            } label: {
                Label("Duplicate", systemImage: "doc.on.doc")
            }

            Divider()

            Button(role: .destructive) {
                deleteNode(at: index)
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    func deleteNode(at index: Int) {
        let nodeId = workflow.nodes[index].id

        // Remove connected edges
        workflow.edges.removeAll { $0.sourceNodeId == nodeId || $0.targetNodeId == nodeId }

        // Remove node
        workflow.nodes.remove(at: index)
        editingNodeId = nil
        selectedNodeIds.remove(nodeId)
    }

    func duplicateNode(at index: Int) {
        let original = workflow.nodes[index]
        let duplicate = WorkflowNode(
            tool: original.tool,
            label: "\((original.label ?? original.tool)) Copy",
            positionX: original.positionX + Double(nodeWidth) + 80,
            positionY: original.positionY + 30,
            inputPorts: original.inputPorts,
            outputPorts: original.outputPorts,
            providerName: original.providerName,
            modelName: original.modelName
        )
        workflow.nodes.insert(duplicate, at: index + 1)
        editingNodeId = duplicate.id
    }
}

// MARK: - Preview

#Preview {
    struct PreviewWrapper: View {
        @State private var scale: CGFloat = 1.0
        @State private var snapToGrid: Bool = true
        @State private var executionObserver = WorkflowExecutionObserver()

        var body: some View {
            WorkflowCanvasView(
                workflow: .constant(Workflow(
                    name: "Test Workflow",
                    nodes: [
                        WorkflowNode(
                            tool: "files",
                            label: "Input Files",
                            positionX: 150,
                            positionY: 200,
                            inputPorts: [],
                            outputPorts: [
                                PortInfo(
                                    id: "files", name: "Files", portType: "output",
                                    dataType: "files", required: true, description: ""
                                )
                            ]
                        ),
                        WorkflowNode(
                            tool: "transcribe",
                            label: "Transcribe",
                            positionX: 350,
                            positionY: 200,
                            inputPorts: [
                                PortInfo(
                                    id: "files", name: "Files", portType: "input",
                                    dataType: "files", required: true, description: ""
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "text", name: "Text", portType: "output",
                                    dataType: "text", required: true, description: ""
                                ),
                                PortInfo(
                                    id: "structured", name: "JSON", portType: "output",
                                    dataType: "json", required: true, description: ""
                                )
                            ]
                        ),
                        WorkflowNode(
                            tool: "to_word",
                            label: "To Word",
                            positionX: 550,
                            positionY: 200,
                            inputPorts: [
                                PortInfo(
                                    id: "content", name: "Content", portType: "input",
                                    dataType: "any", required: true, description: ""
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "file", name: "File", portType: "output",
                                    dataType: "file", required: true, description: ""
                                )
                            ]
                        )
                    ],
                    edges: []
                )),
                scale: $scale,
                snapToGrid: $snapToGrid
            )
            .environment(executionObserver)
            .frame(width: 800, height: 500)
        }
    }

    return PreviewWrapper()
}
