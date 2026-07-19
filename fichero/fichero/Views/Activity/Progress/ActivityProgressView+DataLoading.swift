import OSLog

// MARK: - Data Loading

extension ActivityProgressView {

    /// Seed the shared `WorkflowExecutionStore` from the persisted run (#2546).
    ///
    /// Called when there is no live execution yet (`liveExecution == nil`): for a
    /// run that already finished — or was mid-flight — when Activity opened, this
    /// fetches `getWorkflowRun` and seeds a `WorkflowExecution` into the store.
    /// Because the parent (`ActivityDetailView`) reads the store to compute
    /// `liveExecution`, the Progress tab re-renders with real status/log instead
    /// of "Progress data not available". Running runs get their detailed live
    /// state from subscribe-on-select; this fills the gap for the rest.
    ///
    /// (Previously a disabled stub that fetched `getWorkflowRun` and threw the
    /// result away pending a backend progress-timeline schema.)
    func loadProgressTimeline() async {
        guard let threadId = selectedRun.threadId else { return }
        guard let store = executionStore else {
            activityProgressLogger.info("No WorkflowExecutionStore in environment; skipping seed")
            return
        }

        isLoadingTimeline = true
        defer { isLoadingTimeline = false }

        await store.seedFromPersistedRun(threadId: threadId)
    }
}
