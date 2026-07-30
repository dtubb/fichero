import SwiftUI

// MARK: - Status Views

extension WorkflowOutputLog {

    @ViewBuilder
    func statusBadge(for status: WorkflowStatus) -> some View {
        HStack(spacing: 4) {
            statusIcon(for: status)
            statusText(for: status)
        }
        .font(.caption)
        .foregroundColor(.secondary)
    }

    @ViewBuilder
    func statusIcon(for status: WorkflowStatus) -> some View {
        switch status {
        case .idle:
            Circle()
                .fill(Color.secondary)
                .frame(width: 6, height: 6)
        case .running:
            ProgressView()
                .scaleEffect(0.6)
        case .paused:
            Image(systemName: "pause.circle.fill")
                .foregroundColor(.orange)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        case .cancelled:
            Image(systemName: "stop.circle.fill")
                .foregroundColor(.orange)
        }
    }

    func statusText(for status: WorkflowStatus) -> Text {
        switch status {
        case .idle: return Text("Idle")
        case .running: return Text("Running")
        case .paused: return Text("Paused")
        case .completed: return Text("Completed")
        case .failed: return Text("Failed")
        case .cancelled: return Text("Cancelled")
        }
    }

    @ViewBuilder
    func stepStatusCell(for status: StepStatus?) -> some View {
        HStack(spacing: 4) {
            if let status = status {
                stepStatusView(status)
            } else {
                Text("-")
                    .foregroundColor(.secondary)
            }
        }
        .font(.caption)
    }

    @ViewBuilder
    func stepStatusView(_ status: StepStatus) -> some View {
        switch status {
        case .pending:
            Circle()
                .stroke(Color.secondary, lineWidth: 1)
                .frame(width: 12, height: 12)
        case .running:
            ProgressView()
                .scaleEffect(0.5)
        case .completed(let duration, let cached):
            HStack(spacing: 2) {
                Image(systemName: cached ? "bolt.circle.fill" : "checkmark.circle.fill")
                    .foregroundColor(cached ? .orange : .green)
                    .font(.caption2)
                if let duration = duration {
                    Text(String(format: "%.1fs", duration))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if cached {
                    Text("cache")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        case .failed(let error):
            ErrorStatusCell(error: error)
        }
    }

}
