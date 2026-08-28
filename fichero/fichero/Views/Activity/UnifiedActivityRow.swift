import SwiftUI

/// One run in the unified Activity list (Daniel, 2026-08-28: Activity should
/// read like Mail — one list, each row saying which library, then what is
/// running, its progress, and the step it is on).
///
/// The library leads because it is the disambiguator: five libraries can each
/// be running "Transcribe", and a row that opens with the workflow name makes
/// the reader hunt for whose it is. Mail's unified inbox puts the account on
/// the row for the same reason.
///
/// Replaces the per-library sectioning in `ActivityMonitorWindow`, where every
/// open library got its own `ActivityBrowserView` reserving 160pt whether or
/// not it held a single run — five libraries produced five scrolling lists,
/// five polls and five error pills over mostly empty space.
struct UnifiedActivityRow: View {
    let run: ActivityRun
    /// Opens this run's detail window. Restored after the first cut of this
    /// row dropped the info button the per-library row had, leaving no way to
    /// reach the step trace at all (Daniel, 2026-08-28).
    var onOpenDetails: (() -> Void)?

    @State private var isHovering = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: run.status.icon)
                .font(.body)
                .foregroundStyle(run.status.color)
                .frame(width: 18)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                titleLine
                detailLine
                if let progress = run.progress, run.isLive, progress > 0 {
                    ProgressView(value: progress)
                        .progressViewStyle(.linear)
                        .frame(maxWidth: 220)
                }
            }

            Spacer(minLength: 0)

            if let onOpenDetails {
                Button(action: onOpenDetails) {
                    Image(systemName: "info.circle")
                        .font(.body)
                }
                .buttonStyle(.borderless)
                // Always present for keyboard and VoiceOver users; only drawn
                // at full strength on hover so a long list stays quiet.
                .opacity(isHovering ? 1 : 0.35)
                .accessibilityLabel("Open run details")
                .help("Open this run's step trace in a separate window")
            }
        }
        .padding(.vertical, 5)
        .contentShape(Rectangle())
        .onHover { isHovering = $0 }
        // Double-click opens the trace, the way double-clicking a Mail row
        // opens the message in its own window. The single click stays
        // selection, which is what the detail pane follows.
        .onTapGesture(count: 2) { onOpenDetails?() }
        .accessibilityElement(children: .combine)
    }

    /// `Library · Workflow` — library first, in secondary weight, so the eye
    /// lands on the workflow while still knowing whose run this is.
    private var titleLine: some View {
        HStack(spacing: 5) {
            if let libraryName = run.libraryName, !libraryName.isEmpty {
                Text(libraryName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("·")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            Text(run.workflowName)
                .font(.subheadline)
                .lineLimit(1)
        }
    }

    /// Counts, current step, and time — the things that answer "how far along
    /// is this and what is it doing", which previously required opening the
    /// detail window.
    private var detailLine: some View {
        HStack(spacing: 6) {
            if run.fileCount > 0 {
                Text(fileProgressText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            if let step = run.currentStep, !step.isEmpty {
                Text(step)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if run.errorCount > 0 {
                Text("^[\(run.errorCount) error](inflect: true)")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
            Text(coarseTimeAgo(run.timestamp))
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
    }

    /// "61 of 92" while running; just the total once finished — a completed
    /// run reporting "92/92" is noise, but a FAILED run's partial count is the
    /// most useful number on the row (78 of 92 reviewed before the provider
    /// died is not the same story as a total loss).
    private var fileProgressText: String {
        guard run.isLive, let progress = run.progress, progress > 0, progress < 1 else {
            return "\(run.fileCount) files"
        }
        let done = Int((Double(run.fileCount) * progress).rounded())
        return "\(done) of \(run.fileCount)"
    }

    /// Stable coarse timestamp — does not re-render every second the way
    /// `Text(_, style: .relative)` does, which matters in a list that can hold
    /// every run from every open library.
    private func coarseTimeAgo(_ date: Date) -> String {
        let seconds = Int(-date.timeIntervalSinceNow)
        switch seconds {
        case ..<60:    return "just now"
        case ..<3600:  return "\(seconds / 60) min ago"
        case ..<86400: return "\(seconds / 3600) hr ago"
        default:       return "\(seconds / 86400) days ago"
        }
    }
}
