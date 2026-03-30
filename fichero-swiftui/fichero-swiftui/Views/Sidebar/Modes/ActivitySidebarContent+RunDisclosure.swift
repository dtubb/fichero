import SwiftUI

extension ActivitySidebarContent {

    @ViewBuilder
    func runDisclosure(_ run: ActivityRun) -> some View {
        runRowLabel(run)
            .contentShape(Rectangle())
            .onTapGesture {
                selectedItemId = "run-\(run.id)"
            }
            .listRowInsets(EdgeInsets(top: 2, leading: 14, bottom: 2, trailing: 8))
        .tag("run-\(run.id)")
    }

    @ViewBuilder
    func runRowLabel(_ run: ActivityRun) -> some View {
        HStack(spacing: 8) {
            if run.status == .running {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 16, height: 16)
            } else {
                Image(systemName: run.status.icon)
                    .foregroundStyle(run.status.color)
                    .frame(width: 16)
            }

            Text(activityRunDisplayName(for: run))
                .font(.subheadline)
                .lineLimit(1)

            Spacer()

            if run.status == .running, let progress = run.progress {
                Text("\(Int(progress * 100))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            if run.errorCount > 0 {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .font(.caption)
            }
        }
    }
}
