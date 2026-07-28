import SwiftUI

// MARK: - Import progress (#4203)

/// What a folder import looks like while it runs. Daniel: "I drop a folder and
/// there is no interface updating, and I don't know if it's working or how long
/// it will take."
///
/// So this answers, in order: which library, is it alive, how far along, how
/// fast, how long left, what failed, and how do I stop it.
///
/// Renders from `ImportService.activeIngest`, republished on every poll — the
/// Activity window and the toolbar island read the same value, so they can never
/// disagree about the numbers.
struct IngestProgressView: View {
    let status: IngestTaskStatus
    var libraryName: String?
    /// Toolbar island: one line, no failure list.
    var isCompact: Bool = false
    var onCancel: () -> Void

    var body: some View {
        if isCompact {
            compactBody
        } else {
            fullBody
        }
    }

    // MARK: Compact — the toolbar island

    private var compactBody: some View {
        HStack(spacing: 6) {
            ProgressView()
                .controlSize(.small)
            Text(headline)
                .font(.callout)
                .monospacedDigit()
                .lineLimit(1)
            cancelButton
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilitySummary)
    }

    // MARK: Full — the Activity window

    private var fullBody: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                VStack(alignment: .leading, spacing: 2) {
                    Text(headline)
                        .font(.headline)
                        .monospacedDigit()
                    if let subtitle {
                        Text(subtitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                }
                Spacer()
                cancelButton
            }

            // A determinate bar needs a real total; while the walk is still
            // counting, an indeterminate bar is the honest shape.
            if let fraction {
                ProgressView(value: fraction)
                    .progressViewStyle(.linear)
            }

            if !status.failures.isEmpty {
                failureList
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .contain)
    }

    private var failureList: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(status.failed) failed")
                .font(.caption)
                .foregroundStyle(.orange)
            // Bounded: a 100k-file import can fail thousands of times and the
            // window must not try to render them all.
            ForEach(status.failures.prefix(Self.visibleFailureLimit)) { failure in
                Text("\(URL(fileURLWithPath: failure.path).lastPathComponent) — \(failure.error)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .help(failure.path)
            }
            if status.failures.count > Self.visibleFailureLimit {
                Text("+\(status.failures.count - Self.visibleFailureLimit) more")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    @ViewBuilder
    private var cancelButton: some View {
        if status.isFinished {
            EmptyView()
        } else {
            Button(status.isCancelling ? "Cancelling…" : "Cancel", action: onCancel)
                .buttonStyle(.borderless)
                .disabled(status.isCancelling)
        }
    }

    // MARK: - Text

    private static let visibleFailureLimit = 5

    /// "Scanning…" until the walk has counted — the moment that currently shows
    /// nothing at all. Never "0 of 0", which reads as an empty folder.
    private var headline: String {
        if status.isScanning {
            return isCompact ? "Scanning…" : "Scanning \(folderName)…"
        }
        let processed = status.processed ?? 0
        let total = status.total ?? 0
        return isCompact ? "\(processed)/\(total)" : "Importing \(processed) of \(total)"
    }

    private var subtitle: String? {
        var parts: [String] = []
        if let libraryName { parts.append(libraryName) }
        if status.filesPerSecond > 0 {
            parts.append(String(format: "%.0f files/sec", status.filesPerSecond))
        }
        if let remaining = status.estimatedSecondsRemaining {
            parts.append("about \(Self.durationText(remaining)) left")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var fraction: Double? {
        guard !status.isScanning, let total = status.total, total > 0,
              let processed = status.processed else { return nil }
        return min(Double(processed) / Double(total), 1)
    }

    private var folderName: String {
        URL(fileURLWithPath: status.path).lastPathComponent
    }

    private var accessibilitySummary: String {
        var summary = headline
        if let subtitle { summary += ", \(subtitle)" }
        if status.failed > 0 { summary += ", \(status.failed) failed" }
        return summary
    }

    /// Coarse on purpose: an ETA from a rate that swings between file sizes is
    /// an estimate, and rendering it to the second would overstate it.
    ///
    /// `nonisolated` is LOAD-BEARING: this is a static on a `View`, which is
    /// MainActor-isolated under the macOS 26 SDK, so the static inherits that
    /// isolation. The Swift Testing suite covering it runs on a cooperative
    /// thread, and the off-main call SIGTRAPs the whole test process — killing
    /// unrelated tests and getting misattributed to whichever one was running
    /// (#4201). Unlike an explicit `@MainActor` type, a View's implicit
    /// isolation compiles fine and only fails at runtime.
    nonisolated static func durationText(_ seconds: Double) -> String {
        if seconds < 60 { return "\(Int(seconds.rounded()))s" }
        if seconds < 3600 {
            return "\(Int((seconds / 60).rounded()))m"
        }
        let hours = seconds / 3600
        return String(format: "%.1fh", hours)
    }
}
