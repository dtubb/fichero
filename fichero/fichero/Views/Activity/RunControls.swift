import SwiftUI

// MARK: - Run Controls (#4321)

/// THE run-control strip: one component over one status vocabulary
/// (`WorkflowStatus`), used by both the Activity Monitor toolbar and the
/// Activity Detail stats bar so the two surfaces can never drift apart again.
///
/// Actions are transactional (`WorkflowExecutionStore.perform`): the POST is
/// awaited, the returned state is applied to the threadId-keyed entry, and the
/// SSE stream is (re)subscribed for any non-terminal outcome — so Pause /
/// Resume / Stop visibly transition and Delete removes the row. Failures
/// surface through `onError` (each host owns its presentation).
struct RunControls: View {
    let threadId: String
    let status: WorkflowStatus
    var onError: (String) -> Void

    /// Store is optional so the component renders (disabled) where the
    /// per-library store isn't injected — previews, early launch.
    @Environment(WorkflowExecutionStore.self) private var store: WorkflowExecutionStore?
    @State private var isActing = false

    /// Which controls a run in `status` offers. Pure — pinned by tests.
    /// Non-terminal runs pause/resume and stop; terminal (and idle/seeded)
    /// runs offer only Delete. `nonisolated`: View statics inherit MainActor
    /// under the macOS 26 SDK, and tests must be able to call this off-main
    /// (#4201).
    nonisolated static func actions(for status: WorkflowStatus) -> [WorkflowRunAction] {
        switch status {
        case .running:
            return [.pause, .stop]
        case .paused:
            return [.resume, .stop]
        case .completed, .failed, .cancelled, .idle:
            return [.delete]
        }
    }

    var body: some View {
        ForEach(Self.actions(for: status)) { action in
            Button {
                Task { await act(action) }
            } label: {
                Label(action.label, systemImage: action.systemImage)
            }
            .disabled(isActing || store == nil)
        }
    }

    private func act(_ action: WorkflowRunAction) async {
        guard let store else { return }
        isActing = true
        defer { isActing = false }
        do {
            try await store.perform(action, threadId: threadId)
        } catch {
            onError(error.localizedDescription)
        }
    }
}
