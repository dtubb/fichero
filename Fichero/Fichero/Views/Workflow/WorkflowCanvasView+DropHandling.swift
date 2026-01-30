import SwiftUI

// MARK: - Drop Handling

extension WorkflowCanvasView {
    /// Get default provider and model for a tool based on its category
    func getDefaultsForCategory(_ category: String) async -> (provider: String?, model: String?) {
        guard appState.isBackendRunning else {
            return (nil, nil)
        }

        do {
            let defaults = try await appState.fetchAIDefaults()

            switch category.lowercased() {
            case "audio":
                return (defaults.audioProvider.isEmpty ? nil : defaults.audioProvider,
                        defaults.audioModel.isEmpty ? nil : defaults.audioModel)
            case "vision":
                return (defaults.visionProvider.isEmpty ? nil : defaults.visionProvider,
                        defaults.visionModel.isEmpty ? nil : defaults.visionModel)
            case "text", "llm":
                return (defaults.textProvider.isEmpty ? nil : defaults.textProvider,
                        defaults.textModel.isEmpty ? nil : defaults.textModel)
            case "video":
                return (defaults.videoProvider.isEmpty ? nil : defaults.videoProvider,
                        defaults.videoModel.isEmpty ? nil : defaults.videoModel)
            default:
                return (nil, nil)
            }
        } catch {
            return (nil, nil)
        }
    }

    func handleDrop(providers: [NSItemProvider], at location: CGPoint) -> Bool {
        for provider in providers {
            provider.loadObject(ofClass: NSString.self) { item, _ in
                if let jsonString = item as? String {
                    Task { @MainActor in
                        // Try to decode as ToolInfo JSON first
                        if let data = jsonString.data(using: .utf8),
                           let toolInfo = try? JSONDecoder().decode(ToolInfo.self, from: data) {
                            addNodeFromToolInfo(toolInfo, at: location)
                        } else {
                            // Fallback: treat as plain tool name (legacy)
                            addNodeFromToolName(jsonString, at: location)
                        }
                    }
                }
            }
        }
        return true
    }

    /// Add node from full ToolInfo (preferred - has all metadata)
    func addNodeFromToolInfo(_ toolInfo: ToolInfo, at position: CGPoint) {
        // Find selected node to auto-connect from
        let sourceNode = selectedNodeIds.first.flatMap { selectedId in
            workflow.nodes.first { $0.id == selectedId }
        }

        // Adjust position to avoid overlapping existing nodes
        let adjustedPosition = findNonOverlappingPosition(near: position)

        // Create node with AI defaults in a Task (async context required)
        Task { @MainActor in
            // Get default provider/model for this tool's category
            let (provider, model) = await getDefaultsForCategory(toolInfo.category)

            // Create node with full tool metadata and AI defaults
            let node = WorkflowNode(
                from: toolInfo,
                positionX: adjustedPosition.x,
                positionY: adjustedPosition.y,
                providerName: provider,
                modelName: model
            )
            workflow.nodes.append(node)

            // Auto-connect: if there's a selected node with output ports, connect to new node's input
            if let source = sourceNode,
               let outputPort = source.outputPorts.first,
               let inputPort = node.inputPorts.first {
                let newEdge = WorkflowEdge(
                    sourceNodeId: source.id,
                    targetNodeId: node.id,
                    sourcePortId: outputPort.id,
                    targetPortId: inputPort.id
                )
                workflow.edges.append(newEdge)
            }

            selectedNodeIds = [node.id]
            editingNodeId = node.id
        }
    }

    /// Add node from tool name only (legacy fallback)
    func addNodeFromToolName(_ toolName: String, at position: CGPoint) {
        // Find selected node to auto-connect from
        let sourceNode = selectedNodeIds.first.flatMap { selectedId in
            workflow.nodes.first { $0.id == selectedId }
        }

        // Adjust position to avoid overlapping existing nodes
        let adjustedPosition = findNonOverlappingPosition(near: position)

        let node = WorkflowNode(
            tool: toolName,
            label: toolName.capitalized,
            positionX: adjustedPosition.x,
            positionY: adjustedPosition.y
        )
        workflow.nodes.append(node)

        // Auto-connect: if there's a selected node with output ports, connect to new node's input
        if let source = sourceNode,
           let outputPort = source.outputPorts.first,
           let inputPort = node.inputPorts.first {
            let newEdge = WorkflowEdge(
                sourceNodeId: source.id,
                targetNodeId: node.id,
                sourcePortId: outputPort.id,
                targetPortId: inputPort.id
            )
            workflow.edges.append(newEdge)
        }

        selectedNodeIds = [node.id]
        editingNodeId = node.id
    }

    /// Find a position that doesn't overlap existing nodes
    func findNonOverlappingPosition(near position: CGPoint) -> CGPoint {
        let minDistance: CGFloat = nodeWidth + 20
        var adjusted = position

        // Check for overlaps and adjust
        for _ in 0..<10 {  // Max 10 iterations
            var hasOverlap = false
            for node in workflow.nodes {
                let deltaX = node.positionX - adjusted.x
                let deltaY = node.positionY - adjusted.y
                let distance = hypot(deltaX, deltaY)

                if distance < minDistance {
                    hasOverlap = true
                    // Move position away from the overlapping node
                    if distance > 0 {
                        adjusted.x -= (deltaX / distance) * (minDistance - distance + 10)
                        adjusted.y -= (deltaY / distance) * (minDistance - distance + 10)
                    } else {
                        adjusted.x += minDistance
                    }
                }
            }
            if !hasOverlap { break }
        }

        // Apply grid snapping to final position
        if snapToGrid {
            adjusted.x = snapToGridValue(adjusted.x)
            adjusted.y = snapToGridValue(adjusted.y)
        }

        return adjusted
    }
}
