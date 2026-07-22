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
        service.subscribe(threadId: threadId) { [weak self] event in
            self?.apply(event, threadId: threadId)
        }
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
        let defaults = UserDefaults.standard
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
    /// Cancelled maps to `.failed`, matching `WorkflowExecutionObserver`.
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
            return .failed
        default:
            return .idle
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
