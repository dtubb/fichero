import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

/// Per-library activity store (#2448).
///
/// Single point for activity/run data in the library.  Views never call
/// `ActivityService` directly: they observe `refreshToken` and call
/// `loadRuns()` / `loadItems()` through the store.
///
/// **Live-refresh strategy:**
/// `ActivityStore` listens to `/api/activity/stream`, so runs started in any
/// window or restored by the backend refresh the browser from activity events.
@MainActor
@Observable
final class ActivityStore: ChangeEventConsumer {
    // ─── Service ──────────────────────────────────────────────────────────────
    let activityService: ActivityService

    // ─── Refresh signal (views observe this) ──────────────────────────────────
    /// Bumped whenever an activity SSE event arrives or a reconnect resync fires.
    /// `ActivityBrowserView` observes this to reload its run list.
    var refreshToken: Int = 0
    /// Coalesces activity-frame bursts into one refreshToken bump (see
    /// `applyActivityEvent`).
    let refreshDebouncer = ReloadDebouncer()

    let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStore")
    private let streamService: ActivityStreamService

    /// When set (REMOTE hosts only), folded change frames arriving on
    /// `/api/activity/stream` (#3159) are reconstructed into `ChangeEvent`s and
    /// handed here — wired by `LibraryReference` to the change stream's
    /// `ingest(_:)` so the domain stores update in place, exactly as a native
    /// `/changes/stream` event would (#2479). Nil on local hosts, where those
    /// mutations already arrive on the dedicated change stream (no double-apply).
    var changeRouter: (@MainActor (ChangeEvent) -> Void)?

    // ─── Backend-work surface (#2279) ──────────────────────────────────────────
    /// The most recent in-flight backend task (e.g. an import or batch the engine
    /// or CLI kicked off), or `nil` when nothing is running. Views observe this
    /// for a live progress indicator. Updated in place — a backend-work frame
    /// never bumps `refreshToken`, so it can't trigger a run-list reload.
    var backendWork: BackendWorkStatus?

    /// The most recent "library opened" signal — e.g. the CLI opened a library
    /// out of band (#2279). Views surface it subtly so the user knows the backend
    /// touched a library they didn't open in this window.
    var lastLibraryOpened: LibraryOpenedSignal?

    // MARK: - Run list (#3231, #4960)
    //
    // The store owns the live+history run-list merge (previously assembled
    // inside ActivityBrowserView). Views observe `runs`/`runLoadFailures` and
    // call `rebuildRuns`, passing @Environment deps in. `runs` is patched
    // in place (`patchRun`) — no method here reassigns the whole array.
    var runs: [ActivityRun] = []
    /// A run's tree read that failed, by thread id, in words; cleared by the next read that works.
    var treeReadFailures: [String: String] = [:]
    /// A run's page dots, by the run's job id (`activity.window.page-grid`).
    var pageGrids: [String: ActivityPageGrid] = [:]
    /// Which read a footer line came from: the run list, or the jobs poll (#5469).
    enum LoadSource: Int { case runs, jobs }
    private struct FailureKey: Hashable {
        let library: UUID
        let source: LoadSource
    }
    /// The footer's lines (`activity.window.honest-state`, #5431): one per
    /// library and read whose last load failed, naming the cause. Keyed so the
    /// next successful load of that read clears exactly its own line.
    private var loadFailures: [FailureKey: String] = [:]
    var runLoadFailures: [String] {
        let ordered = loadFailures
            .sorted { ($0.key.library.uuidString, $0.key.source.rawValue) < ($1.key.library.uuidString, $1.key.source.rawValue) }
            .map(\.value)
        // The run list and the jobs poll refused for the same reason say it once.
        var seen: Set<String> = []
        return ordered.filter { seen.insert($0).inserted }
    }

    /// Set ONE footer line, or clear it with nil; untouched when unchanged.
    func setLoadFailure(_ message: String?, library: UUID, source: LoadSource) {
        let key = FailureKey(library: library, source: source)
        if loadFailures[key] != message { loadFailures[key] = message }
    }

    /// The library this store belongs to, named in a jobs-poll footer line (#5469).
    @ObservationIgnored weak var library: LibraryManager.LibraryReference?
    var isRebuildingRuns = false
    /// True when the last `GET /workflow-execution/runs` page was full —
    /// probably a next page to page in. `false` on a short page, or before load.
    var runsHasMore = false
    /// Historical rows fetched so far (reset by `rebuildRuns`) — the `offset`
    /// `loadMoreRuns` pages from.
    var historicalRunsFetched = 0
    /// One page at a time — the old 7-day/100-event ceiling is gone, so the
    /// list can be arbitrarily long ("show ALL items"); page it instead.
    let runsPageSize = 50

    // MARK: - Background jobs (#user-machine-always-useful FIX 2)
    //
    // The single source both the toolbar Activity popover and the full Activity
    // viewer read for live background jobs (embedding, derivative/HTR queues,
    // Kraken Detect Regions, …) + rough process CPU%. `GET /api/activity/jobs`
    // is polled here — global, cheap, no SSE frame for it — and the two
    // surfaces observe these properties, so they cannot disagree about what is
    // running or whether it FAILED. Updated in place, only when the value
    // actually changes (no-wholesale-rerender): a steady 100%-idle poll never
    // invalidates the observing views.
    var backgroundJobs: [ActivityJob] = []
    /// Counts the Find the Documents runs seen to end, a recipe's step among them (`finddocs.review.items`):
    /// Items and the Inspector read their proposals again when it moves.
    private(set) var findDocumentsRunsEnded = 0
    private(set) var processCpuPercent: Double?
    private(set) var cpuCount: Int = 0
    /// Pause Background Work is on (`activity.pause.global`), from the same read.
    var backgroundPaused = false
    /// How background work runs (`activity.mode.start-stop`, #5621), same read:
    /// what the Start / Stop control shows and sets.
    var backgroundMode: ActivityMode = .automatic
    /// This Mac's state (memory, heat, battery, in use, why heavy work waits), same read.
    private(set) var machine: Components.Schemas.MachineState?
    /// The engine's one summary (live blocks, background group, History count), same read
    /// (`activity.popover.same-summary`, #5852).
    private(set) var activitySummary: Components.Schemas.ActivitySummary?
    private var jobsPollTask: Task<Void, Never>?
    /// Says work starting, finishing and failing to VoiceOver (#3724). A test seam only: nil (the app) posts through
    /// `postAnnouncement`. No stored default that names a static: the store is made during app start-up.
    var announce: (@MainActor (String) -> Void)?
    /// Whether a jobs read has landed: the first one announces nothing (`announcement(from:to:)`).
    private var jobsReadOnce = false
    /// This store polls the jobs read, so its mode follows a change made
    /// elsewhere: the Activity window's Start / Stop reads such a store.
    var pollsJobs: Bool { jobsPollTask != nil }
    /// Bumped each time the engine answers a mode set (#5621). A jobs read that
    /// began before it is older than that answer: its mode and pause are not
    /// applied, or a poll in flight while Pause All was chosen put "running" back.
    @ObservationIgnored var modeAnswers = 0
    /// Runs Delete or Clear Failed removed: a live execution still held in the
    /// app's memory does not bring its row back on the next rebuild (#5634).
    @ObservationIgnored var deletedRunIds: Set<String> = []

    // MARK: - Run trees (#5415: the Activity table's run → step → page rows)
    //
    // `GET /api/activity/jobs/{threadId}` per run, keyed by thread id. A tree
    // is fetched when its row is first shown and again when the change stream
    // names its run: ONE key patched, never the whole dictionary replaced.
    var runTrees: [String: ActivityJobNode] = [:]
    /// Runs the engine has no tree for (recorded before the jobs table): not
    /// asked again, their row shows the run alone.
    var runsWithoutTree: Set<String> = []
    var treeFetchesInFlight: Set<String> = []
    /// One pending tree read per run, restarted by each frame of a burst.
    @ObservationIgnored var pendingTreeReads: [String: Task<Void, Never>] = [:]
    let treeReadDelay: Duration = .milliseconds(300)
    /// The log of a row and the rows under it (#5561), newest last, keyed by
    /// the row's job id: one key patched, and only when it changed.
    var jobLogs: [String: [ActivityJobLogLine]] = [:]
    /// Whether a row's log has a warning or an error (the filter row's default); read with the log.
    var jobLogHasProblems: [String: Bool] = [:]
    /// How many problems a row's log has (a Problems read counts its lines), for the closed Log disclosure.
    var jobLogProblemCount: [String: Int] = [:]
    /// The jobs queued behind a kind's row, by kind (`activity.window.expands-to-pages`, #5839).
    var queuedItems: [String: [ActivityQueuedItem]] = [:]
    /// A recipe run's folders done of its folders in all (`activity.run.progress-per-folder`, #5540), keyed
    /// by the run's id: read from its status each time its tree is read, one key patched, only when changed.
    var recipeRunFolders: [String: RecipeRunFolders] = [:]
    /// How many pages a running recipe run reads at once and why (`recipes-run.memory.gate-shown`, #6217), keyed by the
    /// run's id: read from the same status as its folders; removed when the status no longer says.
    var recipeRunPagesAtOnce: [String: RecipeRunPagesAtOnce] = [:]
    /// The recipe run the project window's strip shows (#5576, #5577): the
    /// project's running recipe run, seen on the jobs poll, and once it ends,
    /// that run until the person puts it away. Its words are its tree's
    /// (`runTrees[projectRunId]`), the record the Activity details read.
    var projectRunId: String?
    /// Runs the person put away: never shown on the strip again, across
    /// relaunches (kept under `putAwayKey` in the app's defaults).
    @ObservationIgnored var putAwayRunIds: Set<String> = []
    /// The project's key for the runs put away (`project.runStrip.closed.<project id>`);
    /// nil for a store with no project, which remembers them only while it lives.
    @ObservationIgnored let putAwayKey: String?
    @ObservationIgnored let defaults: UserDefaults
    /// How many put-away run ids are kept: the newest; older runs are never adopted again anyway.
    static let putAwayKept = 50
    /// How often the jobs endpoint is polled. Loopback + a point-in-time read,
    /// so 2s is live enough for a progress bar without adding real load.
    private let jobsPollInterval: Duration = .seconds(2)
    /// Jobs reads that failed in a row, for the reconnect backoff and the one reload when the engine answers again.
    private(set) var jobsPollFailures = 0

    /// The rows shown are the last the engine sent and it has not answered for this many reads in a row (Fable #10): the window
    /// greys them and says so, instead of showing "running" for as long as the engine is down.
    static let staleAfterFailedReads = 3
    var rowsAreStale: Bool { jobsPollFailures >= Self.staleAfterFailedReads }

    /// How long to wait after `failures` failed reads in a row: 2 s, doubling to at most 30 s.
    static func pollInterval(afterFailures failures: Int) -> Duration {
        .seconds(min(30, 2 << min(max(failures, 0), 4)))
    }

    /// `projectKey` names the project the put-away runs are kept for when there is no
    /// `library` (tests); with a library it is the library's id.
    init(service: ActivityService, library: LibraryManager.LibraryReference? = nil,
         defaults: UserDefaults = EngineConfig.defaults, projectKey: String? = nil) {
        self.activityService = service
        self.library = library
        self.streamService = ActivityStreamService(activityService: service)
        self.defaults = defaults
        let key = (library?.id.uuidString ?? projectKey).map { "project.runStrip.closed.\($0)" }
        self.putAwayKey = key
        if let key { putAwayRunIds = Set(defaults.stringArray(forKey: key) ?? []) }
    }

    /// The stream's two hooks (#5912): each failed attempt reads the endpoint again, and the first connect after a drop
    /// reads the run list again. Separate from `start()` so a test can wire them without a live stream.
    func wireStreamRecovery() {
        streamService.onDrop = { [weak self] in self?.reresolveEndpoint() }
        streamService.onReconnected = { [weak self] in self?.refreshToken += 1 }
    }

    var streamServiceForTesting: ActivityStreamService { streamService }

    func start() {
        wireStreamRecovery()
        streamService.start { [weak self] activity in
            self?.applyActivityEvent(activity)
        }
        startJobsPolling()
    }

    func stop() {
        streamService.stop()
        jobsPollTask?.cancel()
        jobsPollTask = nil
    }

    // MARK: - Background-jobs polling

    /// Poll `GET /api/activity/jobs` on a loop until `stop()`. Started by
    /// `start()` so the toolbar's Activity glyph reflects background work even
    /// with no Activity surface open.
    private func startJobsPolling() {
        jobsPollTask?.cancel()
        jobsPollTask = Task { [weak self] in
            // The project just opened: the run its strip showed before a relaunch first (#5576).
            await self?.restoreProjectRun()
            while !Task.isCancelled {
                await self?.refreshBackgroundJobs()
                guard let self else { return }
                try? await Task.sleep(for: jobsPollFailures == 0 ? jobsPollInterval : Self.pollInterval(afterFailures: jobsPollFailures))
            }
        }
    }

    /// Read one jobs snapshot and apply it in place. A poll failure (engine
    /// restarting, brief transport drop) keeps the last snapshot rather than
    /// flapping the surfaces to empty — the next tick recovers.
    func refreshBackgroundJobs() async {
        let answersBefore = modeAnswers
        do {
            let snapshot = try await activityService.getBackgroundJobs()
            // Applied before any other wait, and the mode only if no set was answered meanwhile.
            applyMachineReadings(snapshot, modeIsCurrent: modeAnswers == answersBefore)
            // Started, finished and failed, said once per read where this store is the one polling (#3724).
            if pollsJobs, let said = Self.announcement(from: jobsReadOnce ? backgroundJobs : nil, to: snapshot.jobs) {
                if let announce { announce(said) } else { Self.postAnnouncement(said) }
            }
            jobsReadOnce = true
            if backgroundJobs != snapshot.jobs {
                // A job of its own whose details are open (its tree is loaded,
                // #5561) is re-read when its row changes: the same one-key
                // update a run's tree gets from the change stream.
                let before = Dictionary(backgroundJobs.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
                for job in snapshot.jobs where runTrees[job.id] != nil && before[job.id] != job {
                    scheduleTreeRead(threadId: job.id)
                }
                rereadRecipeRuns(holdingStagesChangedFrom: before, to: snapshot.jobs)
                // One that left the list has ended (done is not listed): its tree is read once more,
                // so its details say how it ended (a recipe run's summary, #5577).
                let listed = Set(snapshot.jobs.map(\.id))
                for id in before.keys where runTrees[id] != nil && !listed.contains(id) {
                    scheduleTreeRead(threadId: id)
                }
                if Self.aFindDocumentsRunEnded(from: backgroundJobs, to: snapshot.jobs) { findDocumentsRunsEnded += 1 }
                backgroundJobs = snapshot.jobs
                EngineRestartPolicy.runningJobs = snapshot.jobs.filter { $0.state == .running }.count
            }
            await followProjectRun(in: snapshot.jobs)
            if let library { setLoadFailure(nil, library: library.id, source: .jobs) }
            jobsPollSucceeded()
        } catch {
            jobsPollFailed(error)
            // A refusal is a standing answer, not a blip: it reaches the footer
            // with its cause, through the run list's own message (#5469).
            // Anything else (a restarting engine) stays quiet; the next tick recovers.
            guard let library, Self.isRefusal(error) else {
                log.debug("ActivityStore: jobs poll failed \(error.localizedDescription, privacy: .public)")
                return
            }
            let message = Self.runLoadFailureMessage(libraryName: library.displayName, error: error)
            log.error("ActivityStore: jobs poll refused: \(message, privacy: .public)")
            setLoadFailure(message, library: library.id, source: .jobs)
        }
    }

    /// A read failed. An engine that is not there (a restart, a held socket gone) is said in words in the footer and read
    /// again with a growing wait; the run list, which loaded once and failed, reloads when the engine answers
    /// (`activity.reconnects-after-engine-restart`).
    func jobsPollFailed(_ error: Error) {
        guard AccessError.classify((error as? ClientError)?.underlyingError ?? error) == .engineUnreachable else { return }
        jobsPollFailures += 1
        // Each failed read dials the endpoint as the engine config says now, not as it was at the first connect.
        reresolveEndpoint()
        if let library {
            setLoadFailure(Self.runLoadFailureMessage(libraryName: library.displayName, error: error),
                           library: library.id, source: .jobs)
        }
    }

    /// How the store reads the endpoint again; the library's by default, replaceable by a test.
    @ObservationIgnored lazy var reresolveEndpoint: () -> Void = { [weak self] in self?.library?.reresolveEndpoint() }

    /// A read succeeded: after failures, the run list is read again (the window reloads on `refreshToken`).
    func jobsPollSucceeded() {
        guard jobsPollFailures > 0 else { return }
        jobsPollFailures = 0
        refreshToken += 1
    }

    /// The jobs read's figures beside its rows (CPU, the pause, the mode, this
    /// Mac's state), each set only when it changed (no wholesale re-render).
    /// `modeIsCurrent` is false for a read older than the last mode set's answer.
    private func applyMachineReadings(_ snapshot: BackgroundJobsSnapshot, modeIsCurrent: Bool) {
        if processCpuPercent != snapshot.processCpuPercent { processCpuPercent = snapshot.processCpuPercent }
        if cpuCount != snapshot.cpuCount { cpuCount = snapshot.cpuCount }
        if modeIsCurrent {
            if backgroundPaused != snapshot.paused { backgroundPaused = snapshot.paused }
            if backgroundMode != snapshot.mode { backgroundMode = snapshot.mode }
        }
        if machine != snapshot.machine { machine = snapshot.machine }
        if activitySummary != snapshot.activity { activitySummary = snapshot.activity }
    }

    /// The rows the window lists up top: live runs and the queues beside them (`activity.window.history-group`).
    var liveJobs: [ActivityJob] { backgroundJobs.filter { !$0.isEarlier } }

    /// The ended, stopped and interrupted rows the engine folded into History (#5851).
    var historyJobs: [ActivityJob] { backgroundJobs.filter(\.isEarlier) }

    private static func isRefusal(_ error: Error) -> Bool {
        switch AccessError.classify((error as? ClientError)?.underlyingError ?? error) {
        case .unauthenticated, .staleBootstrapToken, .deviceAccessExpired, .forbidden: return true
        default: return false
        }
    }

    /// Background jobs the backend reports as FAILED — surfaced distinctly so a
    /// silent failure (Kraken not installed) can't be mistaken for "still
    /// working" and re-run. Derived so both surfaces agree on the set.
    var failedJobs: [ActivityJob] { backgroundJobs.filter { $0.state.isFailed } }

    /// Background jobs still consuming compute — counts toward the toolbar
    /// badge and the popover's active-task list.
    var activeJobs: [ActivityJob] { backgroundJobs.filter { $0.state.isActive } }

    /// True when the activity SSE stream has dropped and runs are no longer
    /// refreshing live (F7). Views show a "live updates paused" pill. Reads the
    /// nested @Observable stream service, so observers of this store re-render
    /// when it flips.
    var liveUpdatesPaused: Bool { streamService.liveUpdatesUnavailable }

    /// What Activity's pill says: "Reconnecting" only while the stream is retrying by itself; a refused stream does not
    /// retry, so it keeps the plain wording (#5912, review 601).
    var livePillMessage: String {
        liveUpdatesAccessDenied ? LiveUpdatesPausedPill.pausedMessage : LiveUpdatesPausedPill.reconnectingMessage
    }

    /// True when the activity stream was refused with a 403 — this device has no
    /// role on the library. A terminal state (no auto-retry): the UI shows an
    /// access-denied affordance rather than a reconnect spinner (#2479).
    var liveUpdatesAccessDenied: Bool { streamService.accessDenied }

    /// Force an immediate reconnect of the activity stream (the pill's action),
    /// rather than waiting out the backoff.
    func reconnectLiveUpdates() {
        stop()
        start()
    }
}
