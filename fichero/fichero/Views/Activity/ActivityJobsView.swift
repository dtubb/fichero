import SwiftUI

/// One live background job, rendered identically wherever the Activity surfaces
/// show it — the toolbar Activity popover AND the full Activity viewer both
/// mount this row from `ActivityStore.backgroundJobs`, so the two cannot drift
/// (#user-machine-always-useful FIX 2).
///
/// A FAILED job is the reason this row exists: a Kraken "Detect Regions" that
/// failed silently is what made Daniel re-run it three times. Failure gets a
/// red glyph, red text and the word "Failed" — never a spinner that reads as
/// "still working".
struct ActivityJobRow: View {
    let job: ActivityJob

    private var isFailed: Bool { job.state.isFailed }

    var body: some View {
        HStack(spacing: 8) {
            leadingGlyph
            VStack(alignment: .leading, spacing: 2) {
                Text(job.name)
                    .font(.callout)
                    .foregroundStyle(isFailed ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
                    .lineLimit(1)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(isFailed ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if !isFailed, job.showsProgress {
                Text("\(job.displayPercent)%")
                    .font(.callout.weight(.medium))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
    }

    @ViewBuilder
    private var leadingGlyph: some View {
        switch job.state {
        case .failed:
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .paused:
            Image(systemName: "pause.circle.fill")
                .foregroundStyle(.orange)
        case .running, .stalled, .other:
            ProgressView()
                .controlSize(.small)
        }
    }

    /// The state, and — for a determinate running job — its counts, so the user
    /// sees both how far along and (when it failed) that it stopped.
    private var subtitle: String? {
        switch job.state {
        case .failed:
            // The reason is the whole point (Daniel re-ran Kraken not knowing it
            // failed "not installed") — show it when the backend recorded one.
            if let reason = job.reason, !reason.isEmpty {
                return "Failed — \(reason)"
            }
            return "Failed"
        case .stalled:
            return job.showsProgress ? "Stalled — \(job.current) of \(job.total)" : "Stalled"
        case .paused:
            return "Paused"
        case .completed:
            return "Completed"
        case .running, .other:
            guard job.showsProgress else { return nil }
            return "\(job.current) of \(job.total)"
        }
    }

    private var accessibilityLabel: String {
        switch job.state {
        case .failed: return "\(job.name), failed"
        case .completed: return "\(job.name), completed"
        case .paused: return "\(job.name), paused"
        case .running, .stalled, .other:
            return job.showsProgress
                ? "\(job.name), \(job.displayPercent) percent"
                : "\(job.name), running"
        }
    }
}

/// Process-wide CPU usage the jobs endpoint reports alongside the jobs, so the
/// user can see how much compute the app is consuming (Daniel: "a way to see
/// how much CPU something is using, to make it clear to the user"). Shown once
/// per surface, not per job — attribution to a single job isn't attempted.
struct ProcessCPULabel: View {
    let percent: Double
    let cpuCount: Int

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "cpu")
                .foregroundStyle(.secondary)
            Text(text)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Processor use \(Int(percent.rounded())) percent")
    }

    /// "CPU 142%" — a process-wide percent where 100 is one core busy; the core
    /// count is appended when known so >100% reads as "more than one core"
    /// rather than an error.
    private var text: String {
        let base = "CPU \(Int(percent.rounded()))%"
        return cpuCount > 0 ? "\(base) of \(cpuCount * 100)%" : base
    }
}

#Preview("Job rows") {
    VStack(alignment: .leading, spacing: 10) {
        ActivityJobRow(job: ActivityJob(
            id: "1", name: "Embedding pages", current: 42, total: 100, percent: 42, state: .running
        ))
        ActivityJobRow(job: ActivityJob(
            id: "2", taskType: "workflow", name: "Detect Regions (Kraken)",
            state: .failed, reason: "Kraken not installed"
        ))
        ActivityJobRow(job: ActivityJob(
            id: "3", name: "Processing imported pages", current: 3, total: 20, percent: 15, state: .stalled
        ))
        Divider()
        ProcessCPULabel(percent: 142, cpuCount: 8)
    }
    .padding()
    .frame(width: 300)
}
