import FicheroAPIClient
import Foundation
import Observation
import OSLog
#if os(macOS)
// @preconcurrency: the UN* types (UNUserNotificationCenter, UNMutableNotificationContent,
// UNNotificationRequest) captured in requestAuthorization's @Sendable completion handler
// are Apple SDK types that predate Sendable annotation — they are the only offenders, so
// the import silences the non-Sendable-capture warnings without changing behavior (#3977).
@preconcurrency import UserNotifications
#endif

/// Shared, per-library home for **live** workflow execution state, keyed by
/// `threadId` (#2546).
///
/// Why this exists: the Activity monitor must show live progress for ANY running
/// workflow, no matter where it was started. Before this store, the live
/// `WorkflowExecution` only flowed while the Workflow editor held the
/// `WorkflowStreamService` SSE subscription — open Activity on a run started
/// elsewhere (or after the editor closed) and progress sat at 0% because nobody
/// was subscribed to that thread's stream.
///
/// This store fixes that with **subscribe-on-select**: when a running run is
/// selected in Activity, `subscribe(threadId:…)` opens (or reuses) the live SSE
/// stream for that thread and reduces its events into a `WorkflowExecution`.
///
/// It does NOT re-parse SSE — it reuses `WorkflowStreamService` (the one
/// streaming code path, converged onto the shared `FicheroClient` transport in
/// #2538) and the shared `WorkflowExecution.apply(_:)` reducer (the same one
/// `WorkflowExecutionObserver` uses). One reducer, two homes: the observer keeps
/// the editor's workflowId-keyed live state; this store owns the Activity
/// monitor's threadId-keyed live state.
///
/// One instance per library (registered on `LibraryReference`, mirroring
/// `ActionStore` / `ResearchStore` / `SearchStore`), shared across that library's
/// windows. See `docs/contributor/architecture/fichero/observable_data_layer.md`.
@MainActor
@Observable
final class WorkflowExecutionStore {
    /// Live (and seeded) executions keyed by `threadId`. Views read this.
    private(set) var executions: [String: WorkflowExecution] = [:]

    /// One `WorkflowStreamService` per subscribed thread. Each owns a single SSE
    /// `streamTask`, so a per-thread instance lets several runs stream at once
    /// without one selection cancelling another's stream. Not observed.
    private var streamServices: [String: WorkflowStreamService] = [:]

    // Transport seams — the SAME generated client + activity wrapper the rest of
    // the library uses. `ficheroClient` mints the per-thread stream services;
    // `activityService` seeds finished/mid-flight runs via `getWorkflowRun`.
    private let ficheroClient: FicheroClient
    private let activityService: ActivityService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExecutionStore")

    /// Typed control-endpoint client for the transactional run actions below
    /// (#4321). Same generated transport as the per-thread stream services.
    @ObservationIgnored
    private lazy var executionService = WorkflowExecutionService(ficheroClient: ficheroClient)

    init(ficheroClient: FicheroClient, activityService: ActivityService) {
        self.ficheroClient = ficheroClient
        self.activityService = activityService
    }

    // MARK: - Reads

    /// The live (or seeded) execution for a thread, if any.
    func execution(forThreadId threadId: String) -> WorkflowExecution? {
        executions[threadId]
    }

    /// Whether a live SSE subscription is currently open for a thread.
    func isSubscribed(threadId: String) -> Bool {
        streamServices[threadId] != nil
    }

    // MARK: - Subscribe-on-select (live runs)

    /// Ensure the store is streaming live progress for a running thread.
    ///
    /// Idempotent: a second call while already subscribed is a no-op, so it is
    /// safe to call from `.task`/`.onChange` every time a run is selected. Seeds
    /// a minimal running execution immediately so the UI has something to show
    /// before the first event lands.
    func subscribe(threadId: String, workflowId: String, name: String) {
        guard streamServices[threadId] == nil else { return }

        if executions[threadId] == nil {
            executions[threadId] = WorkflowExecution(
                id: workflowId,
                name: name,
                threadId: threadId,
                startTime: Date(),
                status: .running,
                nodeStates: [:],
                documentProgress: [:],
                currentFilePath: nil,
                currentNodeId: nil,
                currentNodeName: nil,
                isRunning: true,
                workflowError: nil
            )
        }

        let service = WorkflowStreamService(ficheroClient: ficheroClient)
        streamServices[threadId] = service
        log.info("Activity monitor subscribing to live stream for thread: \(threadId, privacy: .public)")
        service.subscribe(
            threadId: threadId,
            onEvent: { [weak self] event in
                self?.apply(event, threadId: threadId)
            },
            onStreamEnd: { [weak self] in
                Task { @MainActor in
                    await self?.reconcileAfterStreamEnd(threadId: threadId)
                }
            }
        )
    }

    /// Reconcile a run whose SSE stream ended WITHOUT a terminal frame
    /// (#4346/#4349): the transport died (UDS pool starvation, engine restart,
    /// network drop), so no `complete`/`error`/`cancelled` event can ever
    /// arrive and the row's spinner had nothing to stop it. Poll the persisted
    /// run record: a terminal status settles the row; a still-running status
    /// resubscribes a fresh stream (whose own end lands back here, giving
    /// spaced retries). Bounded so a dead engine doesn't poll forever — state
    /// is then left visibly stale and the next Activity populate() retries.
    func reconcileAfterStreamEnd(threadId: String) async {
        // Drop the dead service handle so a reconcile that finds the run
        // still live can attach a fresh stream.
        streamServices.removeValue(forKey: threadId)
        guard executions[threadId]?.isRunning == true else { return }

        for attempt in 0..<12 {
            try? await Task.sleep(for: .seconds(attempt == 0 ? 1 : 5))
            if Task.isCancelled { return }
            // Settled by an event elsewhere, or a fresh subscription exists.
            guard executions[threadId]?.isRunning == true,
                  streamServices[threadId] == nil else { return }
            do {
                try await applyRefreshedThreadStatus(threadId: threadId)
                return
            } catch {
                let reason = error.localizedDescription
                let attemptNumber = attempt + 1
                log.warning(
                    "reconcileAfterStreamEnd: \(threadId, privacy: .public) attempt \(attemptNumber) failed: \(reason, privacy: .public)"
                )
            }
        }
        log.error(
            "reconcileAfterStreamEnd: giving up on \(threadId, privacy: .public) — run state may be stale until Activity repopulates"
        )
    }

    /// Cancel the live stream for a thread (the reduced state is kept so the
    /// Activity tabs stay populated after the run ends).
    func unsubscribe(threadId: String) {
        streamServices[threadId]?.cancelStream()
        streamServices.removeValue(forKey: threadId)
    }

    // MARK: - Seed (finished / mid-flight runs)

    /// Seed the store from the persisted run for a thread that already finished
    /// (or was mid-flight) when Activity opened. This is what powers the Progress
    /// tab for runs the live stream never carried. No-op if an entry already
    /// exists (a live subscription takes precedence — we never clobber live
    /// state with a snapshot).
    func seedFromPersistedRun(threadId: String) async {
        guard executions[threadId] == nil else { return }
        do {
            let run = try await activityService.getWorkflowRun(threadId: threadId)
            executions[threadId] = WorkflowExecution(persistedRun: run)
            log.info("Seeded persisted run for thread: \(threadId, privacy: .public)")
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            log.error(
                "Failed to seed persisted run for \(threadId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    // MARK: - Run controls (#4321)

    /// Execute one user-initiated run action TRANSACTIONALLY: await the POST,
    /// apply the returned state to the threadId-keyed entry in place, and
    /// (re)subscribe the SSE stream for any non-terminal outcome. The old path
    /// (`ActivityViewHelpers.performRunAction`) fired the endpoint and flipped
    /// no local state, so Pause/Resume/Stop never visibly did anything — and a
    /// paused run was never subscribed, so Resume COULD not visibly work.
    func perform(_ action: WorkflowRunAction, threadId: String) async throws {
        switch action {
        case .pause:
            try await executionService.pauseWorkflow(threadId: threadId)
            // Pause/cancel return no body — fetch the authoritative state once.
            // The (re)subscribed stream then carries the async transition.
            try await applyRefreshedThreadStatus(threadId: threadId)
        case .resume:
            let thread = try await executionService.resumeWorkflow(threadId: threadId)
            apply(thread: thread)
        case .stop:
            try await executionService.cancelWorkflow(threadId: threadId)
            try await applyRefreshedThreadStatus(threadId: threadId)
        case .delete:
            try await executionService.deleteThread(threadId: threadId)
            unsubscribe(threadId: threadId)
            executions.removeValue(forKey: threadId)
        }
    }

    /// Fetch the persisted thread status and apply it (pause/cancel POSTs
    /// acknowledge without a body).
    private func applyRefreshedThreadStatus(threadId: String) async throws {
        let thread = try await executionService.getThreadStatus(threadId: threadId)
        apply(thread: thread)
    }

    /// Reduce a control-endpoint response into the store: update the entry in
    /// place, then keep the SSE subscription in sync with liveness — subscribe
    /// any non-terminal run (running OR paused, so a later Resume streams),
    /// drop the stream on a terminal one.
    func apply(thread: ExecutionThread) {
        let execution = Self.reduced(executions[thread.threadId], thread: thread)
        executions[thread.threadId] = execution

        if Self.shouldSubscribe(status: execution.status) {
            subscribe(
                threadId: thread.threadId,
                workflowId: thread.workflowId,
                name: thread.workflowName
            )
        } else {
            unsubscribe(threadId: thread.threadId)
        }
    }

    /// Pure reducer for a control-endpoint `ExecutionThread` response: patch
    /// the existing execution in place (never lose reduced node/file state), or
    /// seed a minimal entry when the run wasn't tracked yet (CLI-launched).
    nonisolated static func reduced(
        _ existing: WorkflowExecution?,
        thread: ExecutionThread
    ) -> WorkflowExecution {
        let status = WorkflowExecution.workflowStatus(from: thread.status)
        var execution = existing ?? WorkflowExecution(
            id: thread.workflowId,
            name: thread.workflowName,
            threadId: thread.threadId,
            startTime: Date(),
            status: status,
            nodeStates: [:],
            documentProgress: [:],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: status == .running,
            workflowError: thread.error
        )
        execution.status = status
        execution.isRunning = status == .running
        execution.workflowError = thread.error
        return execution
    }

    /// A run stays subscribed while it can still change: running streams
    /// progress, paused streams the eventual resume/cancel. Terminal states
    /// drop the stream (#4321 — paused runs were never subscribed, so Resume
    /// could never visibly work).
    nonisolated static func shouldSubscribe(status: WorkflowStatus) -> Bool {
        status == .running || status == .paused
    }

    // MARK: - Event reduction

    private func apply(_ event: WorkflowStreamEvent, threadId: String) {
        guard var execution = executions[threadId] else { return }
        execution.apply(event)            // shared reducer (no duplicated SSE logic)
        executions[threadId] = execution

        switch event {
        case .complete:
            unsubscribe(threadId: threadId)
            WorkflowCompletionNotifier.notify(name: execution.name, outcome: .completed)
        case .error(_, let error), .systemicError(_, let error, _, _):
            unsubscribe(threadId: threadId)
            WorkflowCompletionNotifier.notify(name: execution.name, outcome: .failed(error))
        case .cancelled:
            // User-initiated stop — no notification (the brief is completed/failed only).
            unsubscribe(threadId: threadId)
        default:
            break
        }
    }
}

// MARK: - Run actions (#4321)

/// The user-facing controls on a workflow run. One vocabulary for every
/// surface (Monitor toolbar, Detail stats bar) — see `RunControls`.
enum WorkflowRunAction: String, CaseIterable, Identifiable {
    case pause
    case resume
    case stop
    case delete

    var id: String { rawValue }

    var label: String {
        switch self {
        case .pause: return "Pause"
        case .resume: return "Resume"
        case .stop: return "Stop"
        case .delete: return "Delete"
        }
    }

    var systemImage: String {
        switch self {
        case .pause: return "pause"
        case .resume: return "play.fill"
        case .stop: return "stop"
        case .delete: return "trash"
        }
    }
}

// MARK: - Completion notifications (#1869)

/// Posts a local system notification when a workflow run the app ALREADY observes
/// reaches a terminal state (#1869). Front-end only: it reacts to the same
/// completed/failed events `WorkflowExecutionStore` reduces — it does no backend
/// work and adds no new event plumbing.
///
/// Dead-simple: a single on/off preference (default ON), and authorization is
/// requested lazily the first time a notification is actually posted (the system
/// shows its prompt only once). When the preference is off it posts nothing and
/// never prompts.
enum WorkflowCompletionNotifier {
    /// What finished, carrying the failure message only when it failed.
    enum Outcome {
        case completed
        case failed(String)
    }

    /// The single on/off preference, shared with the Settings toggle. Default ON:
    /// an UNSET key reads as enabled (UserDefaults.bool returns false for unset,
    /// so the presence check is required to make the default ON, not off).
    static let enabledDefaultsKey = "notificationsEnabled"

    static var isEnabled: Bool {
        let defaults = EngineConfig.defaults
        guard defaults.object(forKey: enabledDefaultsKey) != nil else { return true }
        return defaults.bool(forKey: enabledDefaultsKey)
    }

    /// Post a completed/failed notification for a finished run. No-op (and no
    /// authorization prompt) when the preference is off.
    @MainActor
    static func notify(name: String, outcome: Outcome) {
        guard isEnabled else { return }
        #if os(macOS)
        let body: String
        switch outcome {
        case .completed:
            body = "Completed"
        case .failed(let error):
            body = error.isEmpty ? "Failed" : "Failed — \(error)"
        }

        let content = UNMutableNotificationContent()
        content.title = name.isEmpty ? "Workflow" : name
        content.body = body
        content.sound = .default

        let center = UNUserNotificationCenter.current()
        // Lazy, once: requestAuthorization only shows the system prompt the first
        // time; later calls just return the existing decision without a prompt.
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            center.add(UNNotificationRequest(
                identifier: UUID().uuidString,
                content: content,
                trigger: nil  // deliver immediately
            ))
        }
        #endif
    }
}

// MARK: - Seeding a WorkflowExecution from a persisted run

extension WorkflowExecution {
    /// Build a coarse execution snapshot from a persisted `WorkflowRunResponse`.
    ///
    /// The backend does not (yet) persist a per-node / per-document progress
    /// timeline, so `nodeStates` / `documentProgress` stay empty — this carries
    /// status, the execution log, and the error so the Activity Progress tab can
    /// render a finished run instead of "Progress data not available".
    init(persistedRun run: WorkflowRunResponse) {
        let status = WorkflowExecution.workflowStatus(fromRaw: run.status)
        let logLines = run.executionLog?
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map(String.init) ?? []
        self.init(
            id: run.workflowId,
            name: run.workflowName,
            threadId: run.threadId,
            startTime: WorkflowExecution.parseISODate(run.startedAt) ?? Date(),
            status: status,
            nodeStates: [:],
            documentProgress: [:],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: status == .running,
            workflowError: run.error,
            totalFiles: 0,
            processedFiles: 0,
            logLines: logLines
        )
    }

    /// Map the backend's run-status string onto the app `WorkflowStatus`.
    /// Cancelled (and its stop/delete variants) is its own terminal state
    /// (#4321) — it used to collapse onto `.failed`, so a deliberate Stop
    /// rendered as Failed.
    static func workflowStatus(fromRaw raw: String) -> WorkflowStatus {
        switch raw.lowercased() {
        case "running", "in_progress", "started":
            return .running
        case "completed", "complete", "success", "succeeded":
            return .completed
        case "failed", "error":
            return .failed
        case "paused":
            return .paused
        case "cancelled", "canceled", "stopped", "stop_requested", "deleted":
            return .cancelled
        default:
            return .idle
        }
    }

    /// Map the typed control-endpoint status (`ExecutionStatus`, itself mapped
    /// case-for-case from the generated `RunStatus` enum, #4316) onto the app
    /// `WorkflowStatus`. Exhaustive — a new lifecycle state fails compilation
    /// instead of silently misrendering (#4321).
    static func workflowStatus(from status: ExecutionStatus) -> WorkflowStatus {
        switch status {
        case .running:
            return .running
        case .paused:
            return .paused
        case .completed:
            return .completed
        case .failed, .error:
            return .failed
        case .cancelled, .stopped, .deleted:
            return .cancelled
        }
    }

    static func parseISODate(_ string: String?) -> Date? {
        guard let string else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: string) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: string)
    }
}
