import SwiftUI

// MARK: - Activity Run Row

/// A single run in the activity list - used within DisclosureGroup
struct ActivityRunRow: View {
    let run: ActivityRun

    var body: some View {
        HStack(spacing: 8) {
            // Status icon
            if run.status == .running {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 16, height: 16)
            } else {
                Image(systemName: run.status.icon)
                    .foregroundStyle(run.status.color)
                    .frame(width: 16)
            }

            // Run timestamp
            Text(formattedTimestamp)
                .font(.subheadline)
                .lineLimit(1)

            Spacer()

            // Progress for running
            if run.status == .running, let progress = run.progress {
                Text("\(Int(progress * 100))%")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Error indicator
            if run.errorCount > 0 {
                HStack(spacing: 2) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                        .font(.caption)
                    if run.errorCount > 1 {
                        Text("\(run.errorCount)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .contentShape(Rectangle())
    }

    private var formattedTimestamp: String {
        let formatter = DateFormatter()
        let daysSince = Calendar.current.dateComponents([.day], from: run.timestamp, to: Date()).day ?? 0
        if daysSince == 0 {
            formatter.dateFormat = "h:mm a"
        } else if daysSince < 7 {
            formatter.dateFormat = "EEE h:mm a"
        } else {
            formatter.dateFormat = "MMM d, h:mm a"
        }
        return "Run \(formatter.string(from: run.timestamp))"
    }
}
