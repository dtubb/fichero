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
                    // Started at a clock time, and while live, elapsed as a
                    // duration (#5432) — never "N min ago".
                    Text(ActivityTimeText.absolute(run.timestamp))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if run.isLive, let started = run.timestamp {
                        Text(started, style: .timer)
                            .font(.caption)
                            .monospacedDigit()
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
}
