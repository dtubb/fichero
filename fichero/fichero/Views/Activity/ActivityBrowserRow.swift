import SwiftUI

// Extracted from ActivityViewHelpers.swift (file-length limit); internal
// because its one caller, ActivityBrowserView, now lives in another file.
struct ActivityBrowserRow: View {
    let run: ActivityRun
    var showsDetailButton: Bool = false
    var onOpenDetails: (() -> Void)?

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: run.status.icon)
                .font(.body)
                .foregroundStyle(run.status.color)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(run.workflowName)
                    .font(.subheadline)
                    .lineLimit(1)

                if let libraryName = run.libraryName {
                    Text(libraryName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                HStack(spacing: 4) {
                    if run.isLive {
                        Text(run.timestamp, style: .relative)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text(coarseTimeAgo(run.timestamp))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if run.isLive, let progress = run.progress, progress > 0 {
                        ProgressView(value: progress)
                            .frame(maxWidth: 60)
                            .scaleEffect(y: 0.7)
                    }
                }
            }

            Spacer()

            if showsDetailButton, let onOpenDetails {
                Button(action: onOpenDetails) {
                    Image(systemName: "info.circle")
                        .font(.body)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Open activity details")
                .help("Open activity details in a separate window")
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }

    /// Stable coarse timestamp — does not update every second like Text(.relative).
    private func coarseTimeAgo(_ date: Date) -> String {
        let seconds = Int(-date.timeIntervalSinceNow)
        switch seconds {
        case ..<60:      return "just now"
        case ..<3600:    return "\(seconds / 60) min ago"
        case ..<86400:   return "\(seconds / 3600) hr ago"
        default:         return "\(seconds / 86400) days ago"
        }
    }
}
