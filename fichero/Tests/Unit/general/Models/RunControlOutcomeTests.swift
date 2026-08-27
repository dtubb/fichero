@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #4402 / #4346 — Stop and Pause appeared to do nothing.
///
/// The request WAS issued. What was missing was on the way back: pause and
/// cancel are politely-200 endpoints, so a thread the engine has never heard of
/// (a row left behind by a killed engine) answers `200 {"status":"not_running"}`
/// rather than 404 — and the Swift client decoded that body and threw it away.
/// With no signal to act on, the client fell through to polling the run's
/// persisted status, which for a stale row reads `running` out of the database
/// for ever. The spinner spun, the button looked dead, and nothing in the app
/// could tell the difference between "pausing now" and "there is nothing here".
///
/// These tests pin the two pure pieces that fix it: reading the status, and
/// deciding what to do about it.
@Suite("Run-control outcome (#4402 / #4346)")
struct RunControlOutcomeTests {

    // MARK: - Reading the status the engine actually sent

    /// The shape shipping today: the endpoints answer with request verbs, or
    /// with one of the two idempotent dead-ends.
    @Test("today's engine vocabulary parses")
    func currentEngineVocabulary() throws {
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "pause_requested") == .requested)
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "cancel_requested") == .requested)
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "already_terminal") == .alreadyTerminal)
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "not_running") == .notRunning)
    }

    /// The shape landing in parallel: the engine settles stale rows itself and
    /// reports the run's new lifecycle status. BOTH vocabularies must work from
    /// one build — a client that only understood one would break the moment the
    /// two halves shipped out of step.
    @Test("the settled-status vocabulary parses too")
    func settledEngineVocabulary() throws {
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "cancelled") == .settled(.cancelled))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "canceled") == .settled(.cancelled))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "stopped") == .settled(.cancelled))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "deleted") == .settled(.cancelled))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "paused") == .settled(.paused))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "failed") == .settled(.failed))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "error") == .settled(.failed))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "completed") == .settled(.completed))
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "running") == .settled(.running))
    }

    @Test("status matching is case-insensitive")
    func caseInsensitive() throws {
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "NOT_RUNNING") == .notRunning)
        #expect(try WorkflowExecutionService.controlOutcome(fromRawStatus: "Cancel_Requested") == .requested)
    }

    /// A verb this build does not know must be LOUD. Falling through to
    /// `.requested` would restore the exact failure being fixed: a control that
    /// silently does nothing while the UI reports success.
    @Test("an unrecognised status throws instead of guessing")
    func unrecognisedStatusThrows() {
        #expect(throws: WorkflowExecutionError.unrecognizedControlStatus("teleported")) {
            _ = try WorkflowExecutionService.controlOutcome(fromRawStatus: "teleported")
        }
        #expect(throws: (any Error).self) {
            _ = try WorkflowExecutionService.controlOutcome(fromRawStatus: "")
        }
    }

    /// The message names the offending value — a bare "unexpected status" sends
    /// the next reader back to the network log.
    @Test("the unrecognised-status error names the value it saw")
    func unrecognisedStatusErrorIsSpecific() {
        let message = WorkflowExecutionError.unrecognizedControlStatus("teleported").errorDescription
        #expect(message?.contains("teleported") == true)
    }

    // MARK: - Deciding what to do about it

    @Test("an accepted request polls the engine for the real transition")
    func requestedRefreshes() {
        #expect(
            WorkflowExecutionStore.disposition(for: .requested, action: .stop) == .refreshFromServer
        )
        #expect(
            WorkflowExecutionStore.disposition(for: .alreadyTerminal, action: .pause) == .refreshFromServer
        )
    }

    /// The engine already did the work and said so. Taking its word is the
    /// point: the extra status round trip is the part that hangs when the
    /// engine is unhealthy, which is the population this fix is FOR.
    @Test("a settled response is believed in place, with no second round trip")
    func settledIsAppliedDirectly() {
        #expect(
            WorkflowExecutionStore.disposition(for: .settled(.cancelled), action: .stop)
                == .settleLocally(.cancelled, error: nil)
        )
        #expect(
            WorkflowExecutionStore.disposition(for: .settled(.paused), action: .pause)
                == .settleLocally(.paused, error: nil)
        )
    }

    /// THE regression. `not_running` must never route to `refreshFromServer`:
    /// the stale row still reads `running` in the database, so that poll
    /// returns `running` for ever and the spinner never stops. That poll is
    /// literally the old behaviour.
    @Test("not_running settles the row locally — it must never poll")
    func notRunningSettlesLocallyAndNeverPolls() {
        for action in [WorkflowRunAction.stop, .pause] {
            let disposition = WorkflowExecutionStore.disposition(for: .notRunning, action: action)
            #expect(
                disposition != .refreshFromServer,
                Comment(rawValue: "\(action.label) on a stale row polled a status that never changes")
            )
            guard case .settleLocally(let status, let error) = disposition else {
                Issue.record("\(action.label) did not settle a not_running row")
                continue
            }
            #expect(status == .failed)
            #expect(error?.isEmpty == false, "a settled-stale row must say WHY it stopped")
        }
    }

    /// Failed, not cancelled: nothing carried out the user's request, and a run
    /// whose engine died neither completed nor was deliberately stopped. If
    /// this ever flips to `.cancelled` the app reports a clean outcome for an
    /// unclean one.
    @Test("a stale row is failed, not cancelled or completed")
    func staleRowIsFailedNotCancelled() {
        guard case .settleLocally(let status, _) =
            WorkflowExecutionStore.disposition(for: .notRunning, action: .stop) else {
            Issue.record("not_running did not settle")
            return
        }
        #expect(status != .cancelled)
        #expect(status != .completed)
        #expect(status != .running)
        #expect(status == .failed)
    }

    /// Whatever a stale row settles to must be TERMINAL by the store's own
    /// subscribe policy — otherwise the row is resubscribed to a stream that
    /// will never carry an event, which is #4346 all over again.
    @Test("a settled-stale row is terminal, so it is not resubscribed")
    func staleRowIsNotResubscribed() {
        guard case .settleLocally(let status, _) =
            WorkflowExecutionStore.disposition(for: .notRunning, action: .stop) else {
            Issue.record("not_running did not settle")
            return
        }
        #expect(!WorkflowExecutionStore.shouldSubscribe(status: status))
    }

    /// …and terminal means the user is offered the one action that can still
    /// succeed on a row with no engine behind it.
    @Test("a settled-stale row offers Delete")
    func staleRowOffersDelete() {
        guard case .settleLocally(let status, _) =
            WorkflowExecutionStore.disposition(for: .notRunning, action: .stop) else {
            Issue.record("not_running did not settle")
            return
        }
        #expect(RunControls.actions(for: status) == [.delete])
    }

    /// Every outcome is handled. A new case added without a decision here would
    /// otherwise get whatever the compiler's last branch happened to be.
    @Test("every outcome maps to a disposition")
    func everyOutcomeIsDecided() {
        let outcomes: [RunControlOutcome] = [
            .requested, .alreadyTerminal, .notRunning,
            .settled(.running), .settled(.paused), .settled(.completed),
            .settled(.failed), .settled(.cancelled), .settled(.idle)
        ]
        for outcome in outcomes {
            _ = WorkflowExecutionStore.disposition(for: outcome, action: .stop)
        }
    }
}
