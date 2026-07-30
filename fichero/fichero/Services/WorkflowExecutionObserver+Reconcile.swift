import Foundation

// MARK: - Terminal reconciliation for run launchers (#4346/#4349)

extension WorkflowExecutionObserver {
    /// Poll until the run tracked under `threadId()` reaches a terminal state.
    ///
    /// The launchers' old wait loops watched ONLY for a terminal SSE frame or
    /// the reducer's `isRunning` flip. When the stream died without a terminal
    /// frame (UDS connection-pool starvation, engine restart — #4349), nothing
    /// could ever flip it: the loop hung forever and every spinner keyed off
    /// the execution kept spinning (#4346). While no live stream exists for
    /// the thread, this asks the server for the run's PERSISTED status every
    /// ~5s and settles the execution when the record is terminal.
    ///
    /// Returns `true` when the run reached a terminal state (via event,
    /// reducer, or reconciliation); `false` only when the surrounding task was
    /// cancelled first.
    func waitForTerminal(
        stream: WorkflowStreamService,
        threadId: () -> String,
        streamCompleted: () -> Bool
    ) async -> Bool {
        var ticks = 0
        while !streamCompleted() {
            try? await Task.sleep(for: .milliseconds(200))
            if Task.isCancelled { return streamCompleted() }
            let id = threadId()
            guard let exec = activeExecutions[id] else {
                // No longer tracked — settled (and archived) elsewhere.
                return true
            }
            if !exec.isRunning { return true }
            ticks += 1
            guard ticks.isMultiple(of: 25),        // ~5s of no progress
                  !id.hasPrefix("pending:"),       // POST not accepted yet
                  !stream.isStreamingThread(id)    // live stream still open — keep waiting
            else { continue }
            // Dead stream, no terminal frame: the persisted run record is the
            // only remaining truth about this run (#4349).
            guard let thread = try? await stream.fetchThreadStatus(threadId: id) else { continue }
            let status = WorkflowExecution.workflowStatus(from: thread.status)
            guard !WorkflowExecutionStore.shouldSubscribe(status: status) else { continue }
            if var settled = activeExecutions[id] {
                settled.status = status
                settled.isRunning = false
                if settled.workflowError == nil { settled.workflowError = thread.error }
                activeExecutions[id] = settled
            }
            return true
        }
        return true
    }

    /// Whether ANY tracked execution is still running. Terminal cleanup uses
    /// this to decide when clearing residual document busy-state is safe
    /// (#4346): the processing identities are not partitioned per thread.
    var hasRunningExecution: Bool {
        activeExecutions.values.contains { $0.isRunning }
    }
}
