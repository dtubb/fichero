import SwiftUI

/// Xcode-style center status island (#4036 follow-up): ONE `.principal`
/// toolbar element — [engine button] [message area] [activity button] — that
/// says what the app is doing (starting the engine, connecting to libraries,
/// importing, running workflows, errors) beside the window title, instead of
/// scattering a spinner in the leading zone and an activity pill after the
/// view-mode icons.
///
/// The flanking buttons are the EXISTING `EngineStatusToolbarItem` and
/// `ActivityStatusToolbarItem` views hosted unchanged — each keeps its own
/// popover (connection diagnosis + Retry; activity list). This view only adds
/// the layout shell and the aggregated message text.
///
/// Hosted by ONE unconditionally-declared `ToolbarItem` (#3163 guard: only
/// CONTENT varies with state, the item itself never appears/disappears).
struct StatusIslandToolbarItem: View {
    @Environment(AppState.self) private var appState
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(ActivityStore.self) private var activityStore

    let isImporting: Bool
    let importProgress: String?
    let libraryId: UUID
    let libraryName: String
    @Binding var importError: String?

    var body: some View {
        HStack(spacing: 8) {
            EngineStatusToolbarItem()
            message
            ActivityStatusToolbarItem(
                isImporting: isImporting,
                importProgress: importProgress,
                libraryId: libraryId,
                libraryName: libraryName,
                importError: $importError
            )
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 3)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Status")
    }

    private var message: some View {
        let status = StatusIslandMessage.resolve(
            enginePhase: appState.engine.phase,
            engineDiagnosis: appState.engine.diagnosis,
            importError: importError,
            isImporting: isImporting,
            importProgress: importProgress,
            backendWorkLabel: activityStore.backendWork.map(Self.label(for:)),
            runningWorkflows: executionObserver.activeExecutions.count
        )
        return Text(status.text)
            .font(.subheadline)
            .foregroundStyle(status.isError ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
            .lineLimit(1)
            .truncationMode(.tail)
            .frame(minWidth: 120, maxWidth: 260)
    }

    private static func label(for work: BackendWorkStatus) -> String {
        let name = work.taskName.isEmpty ? "Backend work" : work.taskName
        return work.total > 0 ? "\(name) — \(work.displayPercent)%" : name
    }
}

/// The one line the status island shows, chosen by urgency.
///
/// Pure and static on purpose: the precedence between "the engine can't
/// connect" and "an import failed" and "three workflows are running" is real
/// logic with real branches, and keeping it out of the view body is what makes
/// it testable without an engine, a store, or a rendered environment (#4036).
struct StatusIslandMessage: Equatable {
    let text: String
    let isError: Bool

    /// Highest-urgency source first: engine failure → engine booting → import
    /// error → import → engine background work → workflows → idle. Errors
    /// outrank progress because a stalled connection explains why the progress
    /// stopped; engine state outranks import state because an import cannot
    /// proceed without the engine at all.
    static func resolve(
        enginePhase: EngineSession.Phase,
        engineDiagnosis: String?,
        importError: String?,
        isImporting: Bool,
        importProgress: String?,
        backendWorkLabel: String?,
        runningWorkflows: Int
    ) -> StatusIslandMessage {
        switch enginePhase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return .init(text: engineDiagnosis ?? "Engine connection problem", isError: true)
        case .starting:
            return .init(text: "Starting engine…", isError: false)
        case .setupNeeded, .ready:
            break
        }
        if let importError { return .init(text: importError, isError: true) }
        if isImporting { return .init(text: importProgress ?? "Importing…", isError: false) }
        if let backendWorkLabel { return .init(text: backendWorkLabel, isError: false) }
        if runningWorkflows > 0 {
            let text = runningWorkflows == 1
                ? "Running 1 workflow…"
                : "Running \(runningWorkflows) workflows…"
            return .init(text: text, isError: false)
        }
        return .init(text: "Ready", isError: false)
    }
}
