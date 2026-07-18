import SwiftUI

extension TriggerDetailView {

    // MARK: - Configuration Section

    @ViewBuilder
    var configurationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Configuration")
                .font(.headline)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], alignment: .leading, spacing: 12) {
                configField("Workflow", trigger.workflowId)
                configField("Watch Path", trigger.watchPath)
                configField("Recursive", trigger.recursive ? "Yes" : "No")
                configField("Events", trigger.eventsDescription)
                configField("Filter Mode", trigger.filterMode.capitalized)
                configField("Filter", trigger.filterDescription)
                configField("Trigger Count", "\(trigger.triggerCount)")

                if let lastTriggered = trigger.lastTriggeredAt {
                    configField("Last Triggered", lastTriggered)
                }
            }

            // Exclude patterns
            if !trigger.excludePatterns.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Exclude Patterns")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    ForEach(trigger.excludePatterns, id: \.self) { pattern in
                        HStack(spacing: 8) {
                            Image(systemName: "xmark.circle")
                                .foregroundStyle(.red)
                                .frame(width: 20)

                            Text(pattern)
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()
                        }
                        .padding(6)
                        .background(Color(platformColor: .controlBackgroundColor))
                        .cornerRadius(6)
                    }
                }
                .padding(.top, 8)
            }

            // Timing settings
            VStack(alignment: .leading, spacing: 8) {
                Text("Timing")
                    .font(.subheadline)
                    .fontWeight(.medium)

                HStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Debounce")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.1fs", trigger.debounceSeconds))
                            .font(.body)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Batch Delay")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.1fs", trigger.batchDelaySeconds))
                            .font(.body)
                    }
                }
            }
            .padding(.top, 8)

            if trigger.useBatch {
                HStack {
                    Image(systemName: "square.stack.3d.up")
                        .foregroundStyle(Color.accentColor)
                    Text("Batch Mode")
                        .font(.subheadline)
                    Text("(max \(trigger.maxConcurrent) concurrent)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .background(Color.accentColor.opacity(0.1))
                .cornerRadius(8)
            }
        }
    }

    @ViewBuilder
    func configField(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body)
                .lineLimit(2)
        }
    }
}
