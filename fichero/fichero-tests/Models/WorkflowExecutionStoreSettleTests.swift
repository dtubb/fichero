@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #4402 / #4346 — the store must SETTLE a row it has been told is stale, and
/// that settling has to reach the screen.
///
/// The pure decision is covered by `RunControlOutcomeTests`. This suite pins
/// the mutation: the entry actually changes, it stops being live, and the
/// Activity list gets a trigger to rebuild that does not require an engine to
/// be alive — which is the half that kept the spinner spinning even once the
/// store knew better.
@MainActor
@Suite("Run-control settle & UI reflection (#4402 / #4346)")
struct WorkflowExecutionStoreSettleTests {

    /// Under the test host every transport fails fast (#4511), so this
    /// constructs cleanly and dials nothing.
    private func makeStore() -> WorkflowExecutionStore {
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!)
        return WorkflowExecutionStore(
            ficheroClient: client,
            activityService: ActivityService(ficheroClient: client)
        )
    }

    private func runningThread(_ threadId: String = "thread-1") -> ExecutionThread {
        ExecutionThread(
            threadId: threadId,
            workflowId: "wf-1",
            workflowName: "Transcribe",
            status: .running,
            checkpointId: nil,
            error: nil
        )
    }

    // MARK: - The row settles

    @Test("settling a tracked run flips it out of running, in place")
    func settleFlipsTrackedRun() {
        let store = makeStore()
        store.apply(thread: runningThread())
        #expect(store.execution(forThreadId: "thread-1")?.isRunning == true)

        store.settle(threadId: "thread-1", status: .failed, error: "engine gone")

        let execution = store.execution(forThreadId: "thread-1")
        #expect(execution?.status == .failed)
        #expect(execution?.isRunning == false)
        #expect(execution?.workflowError == "engine gone")
        // In place, not replaced: the identity the list keys on survives.
        #expect(execution?.id == "wf-1")
        #expect(execution?.name == "Transcribe")
    }

    /// The user pressed Stop on a row they can SEE. If the store was not
    /// tracking that thread (CLI-launched, or started in another window),
    /// settling must still leave a row behind saying what happened — silently
    /// doing nothing is indistinguishable from the bug.
    @Test("settling an untracked thread seeds a row rather than doing nothing")
    func settleSeedsUntrackedThread() {
        let store = makeStore()
        #expect(store.execution(forThreadId: "ghost") == nil)

        store.settle(threadId: "ghost", status: .failed, error: "engine gone")

        let execution = store.execution(forThreadId: "ghost")
        #expect(execution?.threadId == "ghost")
        #expect(execution?.status == .failed)
        #expect(execution?.isRunning == false)
    }

    @Test("a settled terminal run is no longer subscribed")
    func settleDropsTheSubscription() {
        let store = makeStore()
        store.apply(thread: runningThread())

        store.settle(threadId: "thread-1", status: .failed, error: nil)

        #expect(!store.isSubscribed(threadId: "thread-1"))
    }

    // MARK: - …and the screen finds out

    /// `ActivityBrowserView` rebuilt its list from the activity SSE stream and
    /// nothing else. When the engine is gone there IS no stream, so no event
    /// ever arrived, so a row the store had already settled went on rendering
    /// as running. `controlRevision` is the engine-independent trigger; if it
    /// stops moving, the fix stops reaching the screen.
    @Test("settling bumps the control revision the run list observes")
    func settleBumpsControlRevision() {
        let store = makeStore()
        let before = store.controlRevision

        store.settle(threadId: "thread-1", status: .failed, error: nil)

        #expect(store.controlRevision > before)
    }

    @Test("applying a control response bumps the control revision")
    func applyThreadBumpsControlRevision() {
        let store = makeStore()
        let before = store.controlRevision

        store.apply(thread: runningThread())

        #expect(store.controlRevision > before)
    }

    /// A stream event must NOT bump it: those already drive a refresh through
    /// `ActivityStore.refreshToken`, and two triggers for one change is the
    /// #4186 double-render class.
    @Test("the run list observes the control revision, not just the SSE token")
    func activityBrowserObservesControlRevision() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent("Views/Activity/ActivityViewHelpers.swift"),
            encoding: .utf8
        )
        #expect(source.contains("onChange(of: workflowExecutionStore.controlRevision)"))
        #expect(source.contains("onChange(of: activityStore.refreshToken)"))
    }

    // MARK: - End to end through the outcome

    /// The two engine-free outcomes go all the way through `apply(_:of:)`
    /// without touching the network — which is the property that makes Stop
    /// work on a row whose engine is gone.
    @Test("a not_running outcome settles the row without any engine call")
    func notRunningOutcomeSettlesWithoutDialling() async throws {
        let store = makeStore()
        store.apply(thread: runningThread())

        try await store.apply(.notRunning, of: .stop, threadId: "thread-1")

        let execution = store.execution(forThreadId: "thread-1")
        #expect(execution?.status == .failed)
        #expect(execution?.isRunning == false)
        #expect(execution?.workflowError?.isEmpty == false)
        #expect(!store.isSubscribed(threadId: "thread-1"))
    }

    @Test("a settled outcome is written straight through")
    func settledOutcomeIsWrittenThrough() async throws {
        let store = makeStore()
        store.apply(thread: runningThread())

        try await store.apply(.settled(.cancelled), of: .stop, threadId: "thread-1")

        #expect(store.execution(forThreadId: "thread-1")?.status == .cancelled)
        #expect(store.execution(forThreadId: "thread-1")?.isRunning == false)
    }
}
