import SwiftUI

// MARK: - Historical Progress Views

extension ActivityProgressView {

    @ViewBuilder
    var historicalProgressView: some View {
        if isLoadingTimeline {
            ProgressView("Loading progress data...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let timeline = progressTimeline {
            historicalTimelineView(timeline)
        } else {
            VStack(spacing: 12) {
                // Status badge
                HStack {
                    Image(systemName: ActivityViewHelpers.statusIcon(for: selectedRun.status))
                        .foregroundStyle(ActivityViewHelpers.statusColor(for: selectedRun.status))
                    Text(selectedRun.status.rawValue.capitalized)
                        .font(.headline)
                }

                Text("Completed \(selectedRun.timestamp, style: .relative)")
                    .foregroundStyle(.secondary)

                Text("Progress data not available")
                    .foregroundStyle(.tertiary)
                    .font(.caption)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    func historicalTimelineView(_ timeline: ProgressTimeline) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            // Node-level summary
            let visibleNodes = timeline.nodes.keys
                .filter { activityHumanNodeName($0) != nil }
                .sorted()
            if !visibleNodes.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Node Summary")
                        .font(.headline)

                    ForEach(visibleNodes, id: \.self) { nodeId in
                        if let stats = timeline.nodes[nodeId] {
                            nodeStatsRow(nodeId: nodeId, stats: stats)
                        }
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }

            // Execution timeline (nodes + files); internal nodes hidden
            let visibleSteps = timeline.steps.filter { step in
                if step.isNodeStep { return activityHumanNodeName(step.nodeId) != nil }
                return true
            }
            if !visibleSteps.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Execution Timeline")
                        .font(.headline)

                    ForEach(Array(visibleSteps.enumerated()), id: \.offset) { _, step in
                        if step.isNodeStep {
                            nodeExecutionRow(step)
                        } else if step.isFileStep {
                            fileProgressRow(step)
                                .padding(.leading, 20)
                        }
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    @ViewBuilder
    func nodeStatsRow(nodeId: String, stats: NodeProgressStats) -> some View {
        HStack {
            Image(systemName: "square.stack.3d.up")
                .foregroundStyle(.blue)

            VStack(alignment: .leading, spacing: 4) {
                Text(activityHumanNodeName(nodeId) ?? nodeId)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack(spacing: 16) {
                    Label("\(stats.successCount) success", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Label("\(stats.errorCount) errors", systemImage: "xmark.circle.fill")
                        .foregroundStyle(.red)
                    Text("of \(stats.totalFiles) total")
                        .foregroundStyle(.secondary)
                }
                .font(.caption)
            }

            Spacer()
        }
    }

    @ViewBuilder
    func nodeExecutionRow(_ step: ExecutionStep) -> some View {
        HStack(spacing: 12) {
            Image(systemName: step.status == "success" ? "checkmark.circle.fill" :
                    step.status == "error" ? "xmark.circle.fill" : "circle")
                .foregroundStyle(step.status == "success" ? .green :
                                    step.status == "error" ? .red : .secondary)

            VStack(alignment: .leading, spacing: 4) {
                Text(activityHumanNodeName(step.nodeId) ?? step.nodeId)
                    .font(.caption)
                    .fontWeight(.semibold)

                HStack(spacing: 12) {
                    if let duration = step.durationMs {
                        Text(String(format: "%.1fs", duration / 1000))
                            .font(.caption2)
                    }
                    if let filesProcessed = step.filesProcessed {
                        Text("\(filesProcessed) files")
                            .font(.caption2)
                    }
                    if let artifactsCreated = step.artifactsCreated {
                        Text("\(artifactsCreated) artifacts")
                            .font(.caption2)
                    }
                }
                .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    func fileProgressRow(_ step: ExecutionStep) -> some View {
        HStack(spacing: 12) {
            // Status icon
            Image(systemName: step.status == "success" ? "checkmark.circle.fill" :
                    step.status == "error" ? "xmark.circle.fill" : "circle")
                .foregroundStyle(step.status == "success" ? .green :
                                    step.status == "error" ? .red : .secondary)
                .font(.caption)

            VStack(alignment: .leading, spacing: 4) {
                if let filePath = step.filePath {
                    HStack(spacing: 4) {
                        if let fileIndex = step.fileIndex, let fileTotal = step.fileTotal {
                            Text("[\(fileIndex)/\(fileTotal)]")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        Text(documentNameForPath(filePath))
                            .font(.caption)
                            .lineLimit(1)
                    }
                }

                if let duration = step.durationMs {
                    Text(String(format: "%.2fs", duration / 1000))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if let error = step.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }

            Spacer()
        }
        .padding(.vertical, 2)
    }

    /// The user-facing name for a run's input path.
    ///
    /// Not `doc.name` (#4416, found by the producer guardrail in #4393): a page
    /// child's `name` is the engine's upload temp file, so a workflow run over
    /// a scanned page listed `fichero_upload_c84fgjke.pdf` in its history —
    /// unrecognisable next to the `18590129.pdf` the sidebar showed for the
    /// same material. The render site here was already clean; the raw name was
    /// produced one call frame above it, which is exactly the shape the
    /// line-scoped sweep could not see.
    private func documentNameForPath(_ filePath: String) -> String {
        guard !filePath.isEmpty else { return "Unknown" }

        let all = documentStore.currentDocuments
        if let doc = all.first(where: { $0.path == filePath }) {
            return DocumentTitle.displayName(for: doc, parent: doc.parentId.flatMap { parentId in
                all.first(where: { $0.id == parentId })
            })
        }

        // Nothing loaded matches. The path's last component is the user's own
        // filename for everything except an upload temp — and that one is a
        // storage artifact, never shown.
        let filename = (filePath as NSString).lastPathComponent
        return DocumentTitle.isStorageName(filename) ? DocumentTitle.placeholder : filename
    }
}
