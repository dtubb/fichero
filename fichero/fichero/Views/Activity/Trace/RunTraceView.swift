import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "RunTraceView")

/// Read-only "what actually happened" graph for one workflow run (#4320).
///
/// Renders the run's persisted `workflow_snapshot` as a layered DAG with each
/// node colored by its executed status (from `progress_timeline`); clicking a
/// node opens a step-detail popover with the provider/model actually used,
/// duration, output artifacts (#4313 provenance), and — for failed nodes —
/// the error text behind the standard on-demand affordance.
///
/// Deliberately NOT the editor canvas: no drag, no ports, no editing. It
/// composes the same status vocabulary the editor's node views used before
/// run state moved to Activity (#2546), revived here on a read-only surface.
struct RunTraceView: View {
    let threadId: String

    @Environment(APIClient.self) private var apiClient: APIClient?

    @State private var run: WorkflowRunResponse?
    @State private var loadError: String?
    @State private var isLoading = false
    @State private var selectedNodeId: String?

    private static let nodeSize = CGSize(width: 160, height: 88)

    private var graph: RunTraceGraph? {
        run.flatMap { RunTraceModelBuilder.graph(from: $0) }
    }

    var body: some View {
        Group {
            if isLoading && run == nil {
                ProgressView("Loading run trace…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let loadError {
                ContentUnavailableView(
                    "Couldn't Load Run Trace",
                    systemImage: "exclamationmark.triangle",
                    description: Text(loadError)
                )
            } else if let graph, let run {
                traceCanvas(graph: graph, run: run)
            } else if run != nil {
                ContentUnavailableView(
                    "No Trace Available",
                    systemImage: "point.3.connected.trianglepath.dotted",
                    description: Text("This run predates workflow snapshots, so its graph wasn't recorded.")
                )
            } else {
                // Before `.task` has produced anything (including a run whose
                // load task was cancelled mid-flight): a spinner, not a blank
                // pane. An empty sheet reads as "the control did nothing" (#4358).
                ProgressView("Loading run trace…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task(id: threadId) {
            guard !Task.isCancelled else { return }
            await load()
        }
    }

    @ViewBuilder
    private func traceCanvas(graph: RunTraceGraph, run: WorkflowRunResponse) -> some View {
        let layout = RunTraceLayoutEngine.layout(
            nodes: graph.nodes,
            edges: graph.edges,
            nodeSize: Self.nodeSize
        )

        ScrollView([.horizontal, .vertical]) {
            ZStack(alignment: .topLeading) {
                // Edges under the nodes.
                Path { path in
                    for edge in graph.edges {
                        guard let from = layout.positions[edge.source],
                              let to = layout.positions[edge.target] else { continue }
                        let start = CGPoint(x: from.x + Self.nodeSize.width / 2, y: from.y)
                        let end = CGPoint(x: to.x - Self.nodeSize.width / 2, y: to.y)
                        path.move(to: start)
                        let controlOffset = max(24, (end.x - start.x) / 2)
                        path.addCurve(
                            to: end,
                            control1: CGPoint(x: start.x + controlOffset, y: start.y),
                            control2: CGPoint(x: end.x - controlOffset, y: end.y)
                        )
                    }
                }
                .stroke(Color.secondary.opacity(0.45), lineWidth: 1.5)

                ForEach(graph.nodes) { node in
                    RunTraceNodeView(node: node, size: Self.nodeSize)
                        .position(layout.positions[node.id] ?? .zero)
                        .onTapGesture { selectedNodeId = node.id }
                        .popover(
                            isPresented: Binding(
                                get: { selectedNodeId == node.id },
                                set: { if !$0 { selectedNodeId = nil } }
                            )
                        ) {
                            RunTraceNodeDetail(
                                node: node,
                                artifacts: run.runArtifacts.filter { $0.stepName == node.id }
                            )
                        }
                }
            }
            .frame(width: layout.size.width, height: layout.size.height, alignment: .topLeading)
            .padding(4)
        }
    }

    private func load() async {
        guard let apiClient else {
            loadError = "No connection available."
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            run = try await ActivityService(apiClient: apiClient).getWorkflowRun(threadId: threadId)
            loadError = nil
        } catch {
            logger.error("Failed to load run trace for \(threadId): \(String(describing: error))")
            loadError = error.localizedDescription
        }
    }
}

/// One node card on the trace canvas: status-colored border/icon, label,
/// provider·model subtitle, and duration. Read-only.
struct RunTraceNodeView: View {
    let node: RunTraceNode
    let size: CGSize

    @State private var pulseScale: CGFloat = 1.0

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                // Revived editor pulse (#2546 removed it from the editor;
                // the trace is where run state lives now).
                if node.status == .running {
                    Circle()
                        .fill(statusColor.opacity(0.3))
                        .frame(width: 38, height: 38)
                        .scaleEffect(pulseScale)
                        .animation(
                            .easeInOut(duration: 0.8).repeatForever(autoreverses: true),
                            value: pulseScale
                        )
                        .onAppear { pulseScale = 1.2 }
                }
                Circle()
                    .fill(statusColor)
                    .frame(width: 30, height: 30)
                Image(systemName: statusIcon)
                    .font(.caption)
                    .foregroundStyle(.white)
            }

            Text(node.label)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(1)
                .truncationMode(.middle)

            HStack(spacing: 4) {
                if let subtitle = node.providerModelText {
                    Text(subtitle)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                if let duration = node.durationMs {
                    Text(RunTraceFormat.duration(ms: duration))
                        .monospacedDigit()
                }
            }
            .font(.caption2)
            .foregroundStyle(.secondary)

            if node.status == .failed {
                // Standard error affordance: icon inline, detail on demand
                // (the popover) — never a raw dump on the canvas.
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundStyle(.red)
                    .accessibilityLabel("Step failed — click for details")
            }
        }
        .padding(6)
        .frame(width: size.width, height: size.height)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(platformColor: .windowBackgroundColor))
                .shadow(color: statusColor.opacity(0.25), radius: 3)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(statusColor.opacity(node.status == .pending ? 0.35 : 0.8), lineWidth: 1.5)
        )
        .opacity(node.status == .pending ? 0.6 : 1)
        .contentShape(Rectangle())
        .help(node.label)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(node.label), \(accessibilityStatus)")
    }

    private var statusColor: Color {
        switch node.status {
        case .success: return .green
        case .failed: return .red
        case .running: return .blue
        case .skipped: return .orange
        case .pending: return .gray
        }
    }

    private var statusIcon: String {
        switch node.status {
        case .success: return "checkmark"
        case .failed: return "xmark"
        case .running: return "play.fill"
        case .skipped: return "arrow.uturn.forward"
        case .pending: return "circle.dashed"
        }
    }

    private var accessibilityStatus: String {
        switch node.status {
        case .success: return "completed"
        case .failed: return "failed"
        case .running: return "running"
        case .skipped: return "skipped"
        case .pending: return "not executed"
        }
    }
}

/// Step detail for one trace node: tool, provider/model actually used,
/// duration, output artifacts, and error text for failed nodes.
struct RunTraceNodeDetail: View {
    let node: RunTraceNode
    let artifacts: [WorkflowRunArtifact]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(node.label)
                .font(.headline)

            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
                GridRow {
                    Text("Tool").foregroundStyle(.secondary)
                    Text(node.tool)
                }
                if let providerModel = node.providerModelText {
                    GridRow {
                        Text("Model").foregroundStyle(.secondary)
                        Text(providerModel).textSelection(.enabled)
                    }
                }
                if let duration = node.durationMs {
                    GridRow {
                        Text("Duration").foregroundStyle(.secondary)
                        Text(RunTraceFormat.duration(ms: duration)).monospacedDigit()
                    }
                }
                if let skipReason = node.skipReason {
                    GridRow {
                        Text("Skipped").foregroundStyle(.secondary)
                        Text(skipReason)
                    }
                }
                // #4343 seam: when per-step tokens/cost lands in the
                // timeline, add a "Cost" GridRow here beside Duration.
            }
            .font(.caption)

            if let error = node.error {
                DisclosureGroup {
                    ScrollView {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 120)
                } label: {
                    Label("Error", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }

            if !artifacts.isEmpty {
                Divider()
                Text("Artifacts")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                ForEach(artifacts) { artifact in
                    HStack(spacing: 6) {
                        Image(systemName: "sparkles")
                            .foregroundStyle(.secondary)
                        Text(artifact.artifactType)
                            .font(.caption)
                        if let name = artifact.documentName ?? artifact.sourceDocumentName {
                            Text(name)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }
                }
            }
        }
        .padding(12)
        .frame(minWidth: 240, maxWidth: 340, alignment: .leading)
    }
}

enum RunTraceFormat {
    /// "850ms", "3.2s", "2m 05s" — compact durations for node cards.
    static func duration(ms: Double) -> String {
        if ms < 1000 { return String(format: "%.0fms", ms) }
        let seconds = ms / 1000
        if seconds < 60 { return String(format: "%.1fs", seconds) }
        let minutes = Int(seconds) / 60
        let rest = Int(seconds) % 60
        return String(format: "%dm %02ds", minutes, rest)
    }
}

/// Sheet wrapper used by surfaces outside Activity (e.g. the artifact
/// detail's "Produced by" link, #4319) to show a run's trace.
struct RunTraceSheet: View {
    let threadId: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            RunTraceView(threadId: threadId)
                .navigationTitle("Run Trace")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
        .frame(minWidth: 560, minHeight: 420)
    }
}
