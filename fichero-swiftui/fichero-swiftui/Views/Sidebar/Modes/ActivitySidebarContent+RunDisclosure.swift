import SwiftUI

extension ActivitySidebarContent {

    @ViewBuilder
    func runDisclosure(_ run: ActivityRun) -> some View {
        DisclosureGroup(
            isExpanded: Binding(
                get: { isRunExpanded(run.id) },
                set: { setRunExpanded(run.id, expanded: $0) }
            )
        ) {
            ForEach(ActivityChildType.allCases, id: \.self) { childType in
                childRow(childType, for: run)
            }
        } label: {
            runRowLabel(run)
        }
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

    @ViewBuilder
    func childRow(_ childType: ActivityChildType, for run: ActivityRun) -> some View {
        HStack(spacing: 8) {
            Image(systemName: childType.icon)
                .foregroundStyle(childType == .errors && run.errorCount > 0 ? .orange : .secondary)
                .frame(width: 16)

            Text(childType.label)
                .font(.subheadline)

            Spacer()

            if childType == .errors && run.errorCount > 0 {
                Text("\(run.errorCount)")
                    .font(.caption2)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.orange.opacity(0.2), in: Capsule())
            }
        }
        .tag("run-\(run.id)-\(childType.rawValue)")
    }
}
