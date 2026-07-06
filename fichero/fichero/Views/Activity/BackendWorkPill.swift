import SwiftUI

/// Live indicator for backend work the engine or CLI is doing out of band —
/// imports, batches, indexing (#2279). Mirrors `LiveUpdatesPausedPill`'s capsule
/// so the two read as one family, and rides the same `.overlay(alignment: .top)`
/// slot. Observes `ActivityStore.backendWork`; the caller renders it only when
/// that is non-nil.
struct BackendWorkPill: View {
    let status: BackendWorkStatus

    private var showsProgress: Bool { status.total > 0 }

    var body: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
            Text(status.taskName.isEmpty ? "Backend work" : status.taskName)
                .font(.callout)
                .lineLimit(1)
            if showsProgress {
                Text("\(status.displayPercent)%")
                    .font(.callout.weight(.medium))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.thinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(.separator))
        .shadow(radius: 2, y: 1)
        .padding(.top, 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            showsProgress
                ? "\(status.taskName), \(status.displayPercent) percent"
                : "\(status.taskName) running"
        )
    }
}

#Preview("Determinate") {
    BackendWorkPill(status: BackendWorkStatus(
        runId: "t1", phase: .progress, taskType: "import", taskName: "Importing photos",
        status: "running", message: "", current: 42, total: 100, percent: 42, timestamp: ""
    ))
    .padding()
}

#Preview("Indeterminate") {
    BackendWorkPill(status: BackendWorkStatus(
        runId: "t2", phase: .started, taskType: "index", taskName: "Rebuilding index",
        status: "running", message: "", current: 0, total: 0, percent: 0, timestamp: ""
    ))
    .padding()
}
