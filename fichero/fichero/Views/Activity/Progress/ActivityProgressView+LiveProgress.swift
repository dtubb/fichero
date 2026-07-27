import SwiftUI

// MARK: - Live Progress Views

extension ActivityProgressView {

    @ViewBuilder
    func liveProgressView(_ execution: WorkflowExecution) -> some View {
        // Overall progress card
        VStack(alignment: .leading, spacing: 8) {
            Text("Overall Progress")
                .font(.headline)

            if let progress = execution.overallProgress {
                ProgressView(value: progress)
                    .scaleEffect(y: 2)

                HStack {
                    Text("\(Int(progress * 100))%")
                        .font(.title.monospacedDigit())

                    Spacer()

                    if execution.totalFiles > 0 {
                        Text("\(execution.processedFiles) of \(execution.totalFiles) files")
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))

        // Per-node progress (internal LangGraph nodes filtered out)
        let visibleNodes = execution.nodeStates.values
            .filter { activityHumanNodeName($0.nodeId) != nil }
            .sorted { $0.nodeId < $1.nodeId }
        if !visibleNodes.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Node Progress")
                    .font(.headline)

                ForEach(visibleNodes, id: \.nodeId) { state in
                    nodeProgressRow(state)
                }
            }
            .padding()
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }

        // Document progress
        if !execution.documentProgress.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Recent Files")
                    .font(.headline)

                ForEach(execution.orderedDocumentProgress.prefix(10)) { doc in
                    documentProgressRow(doc)
                }
            }
            .padding()
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    @ViewBuilder
    func nodeProgressRow(_ state: NodeExecutionState) -> some View {
        HStack {
            // Status icon
            statusIcon(for: state.status)

            Text(state.displayName ?? activityHumanNodeName(state.nodeId) ?? state.nodeId)
                .lineLimit(1)

            Spacer()

            // Progress or counts
            if state.fileTotal > 0 {
                Text("\(state.successCount)/\(state.fileTotal)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)

                if state.errorCount > 0 {
                    Text("(\(state.errorCount) errors)")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            } else {
                ProgressView(value: state.progress)
                    .frame(width: 60)
            }
        }
    }

    @ViewBuilder
    func documentProgressRow(_ doc: DocumentProgress) -> some View {
        HStack {
            // Overall status
            if doc.stepStatuses.values.contains(where: {
                if case .failed = $0 { return true }
                return false
            }) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.red)
            } else if doc.stepStatuses.values.contains(where: {
                if case .running = $0 { return true }
                return false
            }) {
                ProgressView()
                    .scaleEffect(0.6)
            } else {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            }

            Text(activityCleanFilename(doc.documentName))
                .lineLimit(1)

            Spacer()

            // #700: cache-hit badge. Backend already emits `cached: true` on
            // file_complete events when kreuzberg returns a cached artifact;
            // it lands in StepStatus.completed(duration:cached:). Show a
            // small lightning bolt so users can see which files were served
            // from cache vs freshly processed.
            if doc.stepStatuses.values.contains(where: {
                if case .completed(_, let cached) = $0 { return cached }
                return false
            }) {
                Image(systemName: "bolt.fill")
                    .foregroundStyle(.yellow)
                    .help("Served from cache")
            }
        }
        .font(.caption)
    }

    @ViewBuilder
    func statusIcon(for status: NodeExecutionStatus) -> some View {
        switch status {
        case .running, .parallelRunning:
            ProgressView()
                .scaleEffect(0.6)
                .frame(width: 16, height: 16)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(.red)
        default:
            Image(systemName: "circle")
                .foregroundStyle(.secondary)
        }
    }
}
