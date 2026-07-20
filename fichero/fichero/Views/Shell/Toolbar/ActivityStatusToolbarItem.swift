import SwiftUI

/// Trailing (Xcode-style) toolbar activity indicator (startup-transport-ux
/// S1). Aggregates every source of "something is running in the
/// background" into one small glyph + tap-for-detail popover, rather than
/// each source growing its own pill:
///   • running workflow executions (`WorkflowExecutionObserver`)
///   • the per-library backend-work signal (`ActivityStore.backendWork`) —
///     imports/batches/indexing the engine or CLI kicked off out of band
///   • the in-window document import (`ContentView`'s own `isImporting` /
///     `importProgress` / `importError` state, unchanged from before)
///
/// Idle renders nothing — this item stays unobtrusive. Hosted by the
/// unconditionally-declared `ContentToolbarID.activityStatus` item in
/// `ContentView+Toolbar.swift`; only this view's CONTENT should ever vary,
/// never the `ToolbarItem` itself (#3163 guard — see
/// `EngineStatusToolbarItem`'s doc comment for why).
struct ActivityStatusToolbarItem: View {
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(ActivityStore.self) private var activityStore

    let isImporting: Bool
    let importProgress: String?
    @Binding var importError: String?

    @State private var showPopover = false

    private var activeWorkflows: [WorkflowExecution] {
        Array(executionObserver.activeExecutions.values)
    }

    /// Count of distinct active tasks — workflows + the single backend-work
    /// slot + the in-window import. Drives the badge in the glyph and the
    /// popover's row list.
    private var activeCount: Int {
        activeWorkflows.count
            + (activityStore.backendWork != nil ? 1 : 0)
            + (isImporting ? 1 : 0)
    }

    private var hasError: Bool { importError != nil }

    var body: some View {
        Group {
            if hasError {
                Button {
                    showPopover = true
                } label: {
                    Image(systemName: "exclamationmark.circle.fill")
                        .foregroundStyle(.red)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Activity error")
                .help("A background task reported an error — click for details")
            } else if activeCount > 0 {
                Button {
                    showPopover = true
                } label: {
                    HStack(spacing: 4) {
                        ProgressView()
                            .controlSize(.small)
                        if activeCount > 1 {
                            Text("\(activeCount)")
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Active tasks")
                .help("Active tasks — click to view")
            }
            // Idle (no error, nothing active): render nothing. The
            // ToolbarItem itself stays declared — only its content is empty.
        }
        .popover(isPresented: $showPopover) {
            popoverContent
        }
        .accessibilityLabel(accessibilityLabel)
    }

    @ViewBuilder
    private var popoverContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Activity")
                .font(.headline)

            if let importError {
                HStack {
                    Label(importError, systemImage: "exclamationmark.circle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                    Spacer()
                    Button("Dismiss") { self.importError = nil }
                        .buttonStyle(.borderless)
                }
            }

            if isImporting {
                Label(importProgress ?? "Importing…", systemImage: "square.and.arrow.down")
                    .font(.callout)
            }

            if let backendWork = activityStore.backendWork {
                BackendWorkPill(status: backendWork)
            }

            ForEach(activeWorkflows, id: \.threadId) { execution in
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(execution.name)
                            .font(.callout)
                            .lineLimit(1)
                        if let step = execution.currentNodeName {
                            Text(step)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
            }

            if activeCount == 0 && !hasError {
                Text("Nothing running.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(minWidth: 260, alignment: .leading)
    }

    private var accessibilityLabel: String {
        if hasError { return importError ?? "Import error" }
        if activeCount > 0 { return "\(activeCount) task\(activeCount == 1 ? "" : "s") running" }
        return "No activity"
    }
}
