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

        // Per-node progress
        if !execution.nodeStates.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Node Progress")
                    .font(.headline)

                ForEach(
                    Array(execution.nodeStates.values.sorted(by: { $0.nodeId < $1.nodeId })),
                    id: \.nodeId
                ) { state in
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

            Text(state.nodeId)
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

            Text(doc.documentName)
                .lineLimit(1)

            Spacer()
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
