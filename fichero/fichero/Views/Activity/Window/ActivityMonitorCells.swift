import SwiftUI

extension ActivityMonitorWindow {
    static func find(_ id: ActivityMonitorRow.ID, in rows: [ActivityMonitorRow]) -> ActivityMonitorRow? {
        for row in rows {
            if row.id == id { return row }
            if let found = find(id, in: row.children ?? []) { return found }
        }
        return nil
    }
}

// MARK: - Cells (small, so the hierarchical Table type-checks quickly)

/// The row's name; a run's project before it when rows are not grouped.
struct ActivityNameCell: View {
    let row: ActivityMonitorRow
    let showsProject: Bool

    var body: some View {
        HStack(spacing: 5) {
            // What kind of row it is (#5560): a run, a step, a page, a model load, training.
            Image(systemName: row.kindSymbol)
                .foregroundStyle(.secondary)
                .accessibilityLabel(row.kindWord)
            if showsProject, let project = row.projectName, !project.isEmpty {
                Text(project).foregroundStyle(.secondary)
                Text("·").foregroundStyle(.tertiary)
            }
            Text(row.name).lineLimit(1)
        }
        .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id)")
    }
}

/// The state with its reason: a failed row says why, a waiting row what for.
struct ActivityStateCell: View {
    let row: ActivityMonitorRow

    var body: some View {
        HStack(spacing: 5) {
            // A waiting row looks waiting: a grey clock and grey words, never the running glyph (#5839).
            Image(systemName: row.looksWaiting ? ActivityMonitorRow.Phase.waiting.symbol : row.phase.symbol)
                .foregroundStyle(row.looksWaiting ? Color.secondary : color)
                .accessibilityHidden(true)
            Text(row.stateText)
                .lineLimit(1)
                .foregroundStyle(row.phase == .failed ? AnyShapeStyle(.red)
                    : row.looksWaiting ? AnyShapeStyle(.secondary) : AnyShapeStyle(.primary))
        }
        .help([row.stateText, row.accountDetail].compactMap { $0 }.joined(separator: "\n"))
    }

    private var color: Color {
        switch row.phase {
        case .running: .blue
        case .waiting: .secondary
        case .paused, .cancelled: .orange
        case .failed: .red
        case .done: .green
        }
    }
}

/// How long it took; a run this window is watching ticks as a timer.
struct ActivityElapsedCell: View {
    let row: ActivityMonitorRow

    var body: some View {
        if row.isLive, !row.looksWaiting, let started = row.started {
            Text(started, style: .timer).monospacedDigit()
        } else {
            Text(row.secondsText).monospacedDigit()
        }
    }
}

/// Pause or Resume, and Stop, on a row that is still working; on a finished
/// run with pages it did not do, its one offer ("Read the 3 pages that failed").
struct ActivityRowControls: View {
    let row: ActivityMonitorRow
    /// Stop and Read Again: the same items the context menu and Project › Activity render (#5652).
    let run: ActivityRunMenuTarget
    let perform: (ActivityMonitorRow.Control) -> Void
    let showDetails: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            if let offer = row.readAgainLabel {
                ActivityReadAgainMenuItem(target: run)
                    .labelStyle(.iconOnly)
                    .buttonStyle(.borderless)
                    .help(offer)
                    .accessibilityLabel(offer)
                    .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).readAgain")
            }
            ForEach(row.controls) { control in
                Group {
                    if control == .stop {
                        ActivityStopMenuItem(target: run)
                    } else {
                        Button {
                            perform(control)
                        } label: {
                            Label(control.label, systemImage: control.systemImage)
                        }
                    }
                }
                .labelStyle(.iconOnly)
                .buttonStyle(.borderless)
                .help("\(control.label) \(row.name)")
                .accessibilityLabel("\(control.label) \(row.name)")
                .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).\(control == .stop ? "cancel" : control.rawValue)")
            }
            // Far right (#5560): the row's log and details, as double-click opens them.
            Spacer(minLength: 0)
            if row.opensDetails {
                Button(action: showDetails) {
                    Label("Show Details", systemImage: "info.circle")
                        .labelStyle(.iconOnly)
                }
                .buttonStyle(.borderless)
                .help("Show the log and details of \(row.name)")
                .accessibilityLabel("Show details of \(row.name)")
                .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).info")
            }
        }
    }
}

struct ActivityFooterLine: View {
    let message: String
    let onDismiss: (() -> Void)?

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
            Spacer(minLength: 8)
            if let onDismiss {
                Button("Dismiss", action: onDismiss)
                    .font(.caption)
                    .buttonStyle(.borderless)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.regularMaterial)
    }
}
