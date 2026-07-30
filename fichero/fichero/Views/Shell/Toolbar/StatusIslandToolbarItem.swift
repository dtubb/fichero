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
    /// Optional: the island renders before any library is open (#4203).
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?

    let isImporting: Bool
    let importProgress: String?
    let libraryId: UUID
    let libraryName: String
    @Binding var importError: String?

    var body: some View {
        HStack(spacing: 8) {
            EngineStatusToolbarItem()
            // A live folder import replaces the generic message with real
            // numbers and a Cancel — the island is where the user looks first,
            // and "importing…" with no count is what #4203 is about.
            if let library = libraryManager?.importingLibrary,
               let ingest = library.importService.activeIngest {
                IngestProgressView(
                    status: ingest,
                    libraryName: library.displayName,
                    isCompact: true,
                    onCancel: { Task { await library.importService.cancelActiveIngest() } }
                )
            } else if let library = libraryManager?.importingLibrary {
                // #4235: importing, but the engine has no task yet — staging,
                // the folder grant and the create call all precede it. Show
                // that the drop registered rather than nothing at all. No
                // Cancel: there is no task to cancel until the engine has one.
                ProgressView()
                    .controlSize(.small)
                Text("Preparing import to \(library.displayName)…")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                message
            }
            ActivityStatusToolbarItem(
                isImporting: isImporting,
                importProgress: importProgress,
                libraryId: libraryId,
                libraryName: libraryName,
                importError: $importError
            )
        }
        // No painted background (#4360). On macOS 26 the toolbar itself wraps
        // this principal item in the system's Liquid Glass; the old
        // `.quaternary.opacity(0.5)` fill sat ON TOP of that glass as an
        // opaque plate — white-ish in dark appearance, where `.quaternary`
        // resolves from a white primary. Native chrome means letting NSToolbar
        // own the material; the island supplies content only.
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Status")
    }

    private var message: some View {
        let status = StatusIslandMessage.resolve(
            enginePhase: appState.engine.phase,
            // The MAPPED short title, never the engine's raw diagnosis (#4366):
            // the debug-external diagnosis is a multi-line
            // `PYTHONPATH=src python -m fichero_server.api` invocation, and the
            // island rendered it truncated to a fragment of a shell command.
            // Detail belongs in the popover; the line carries the short form.
            engineStatusTitle: ConnectionPresentation.status(
                phase: appState.engine.phase,
                ownership: ConnectionPresentation.EngineOwnership.current(),
                accessError: appState.backendAccessError,
                authBroken: appState.authBroken
            ).title,
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
    /// - Parameter engineStatusTitle: the SHORT title from
    ///   `ConnectionPresentation.status(…)` — the same words the engine popover
    ///   puts at the top of the same failure. Never a raw diagnosis or a
    ///   transport error string (#4366/#4269/#4380).
    static func resolve(
        enginePhase: EngineSession.Phase,
        engineStatusTitle: String,
        importError: String?,
        isImporting: Bool,
        importProgress: String?,
        backendWorkLabel: String?,
        runningWorkflows: Int
    ) -> StatusIslandMessage {
        switch enginePhase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return .init(text: engineStatusTitle, isError: true)
        case .starting:
            return .init(text: engineStatusTitle, isError: false)
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
