import SwiftUI

/// Overview view showing summary of workflow run
struct ActivityOverviewView: View {
    let selectedRun: SelectedActivityRun
    let activityItems: [ActivityItem]
    let liveExecution: WorkflowExecution?
    let errorCount: Int

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Status card
                statusCard

                // Quick stats
                if let execution = liveExecution {
                    liveStatsCard(execution)
                } else {
                    historicalStatsCard
                }

                // Recent activity
                if !activityItems.isEmpty {
                    recentActivityCard
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private var statusCard: some View {
        VStack(spacing: 8) {
            Image(systemName: statusIcon)
                .font(.system(size: 40))
                .foregroundStyle(statusColor)

            Text(statusText)
                .font(.headline)

            Text(selectedRun.timestamp, format: .dateTime)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func liveStatsCard(_ execution: WorkflowExecution) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Progress")
                .font(.headline)

            if let progress = execution.overallProgress {
                ProgressView(value: progress)
                    .scaleEffect(y: 1.5)

                HStack {
                    Text("\(Int(progress * 100))%")
                        .font(.title2.monospacedDigit())

                    Spacer()

                    if execution.totalFiles > 0 {
                        Text("\(execution.processedFiles) of \(execution.totalFiles) files")
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if let currentFile = execution.currentFileName {
                HStack {
                    Text("Current:")
                        .foregroundStyle(.secondary)
                    Text(currentFile)
                        .lineLimit(1)
                }
                .font(.caption)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private var historicalStatsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Summary")
                .font(.headline)

            HStack(spacing: 20) {
                statItem(title: "Events", value: "\(activityItems.count)")
                statItem(title: "Errors", value: "\(errorCount)", color: errorCount > 0 ? .red : nil)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func statItem(title: String, value: String, color: Color? = nil) -> some View {
        VStack {
            Text(value)
                .font(.title2.monospacedDigit())
                .foregroundStyle(color ?? .primary)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var recentActivityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Activity")
                .font(.headline)

            ForEach(activityItems.prefix(5)) { item in
                HStack(spacing: 8) {
                    Image(systemName: item.typeIcon)
                        .foregroundStyle(ActivityViewHelpers.levelColor(item.level))
                        .frame(width: 16)

                    Text(item.message)
                        .font(.caption)
                        .lineLimit(1)

                    Spacer()

                    if let date = item.parsedTimestamp {
                        Text(date, style: .time)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var statusIcon: String {
        ActivityViewHelpers.statusIcon(for: selectedRun.status)
    }

    private var statusColor: Color {
        ActivityViewHelpers.statusColor(for: selectedRun.status)
    }

    private var statusText: String {
        ActivityViewHelpers.statusText(for: selectedRun.status)
    }
}
