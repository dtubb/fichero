import Foundation
import Observation

/// One sidebar row's activity, observed on its own (the sidebar churn, 2026-11-17): a row reads only its box, so a
/// store change re-renders only the rows whose activity changed. Before, every row read `childActivityCounts` straight
/// from the store, which registered it on `revision`, `currentDocuments` and the status overrides; every change-stream
/// batch (about once a second while work runs) re-ran every visible row's body.
@MainActor
@Observable
final class RowActivityBox {
    /// What the row resolves its activity from (`ContainerActivity.resolve`, the one policy): whether the document is
    /// itself busy, and its children busy of their total. Written only when it changes.
    struct Inputs: Equatable {
        var isSelfProcessing = false
        var busyChildren = 0
        var totalChildren = 0
    }

    /// The store's weak hold on a row's box: the row owns the box, so a row that leaves the sidebar frees it and the
    /// store stops recomputing it.
    struct Weak {
        weak var box: RowActivityBox?
    }

    private(set) var inputs = Inputs()

    fileprivate func set(_ value: Inputs) {
        if inputs != value { inputs = value }
    }
}

@MainActor extension DocumentStore {
    /// The box a sidebar row reads for its document; the caller keeps it, the store holds it weakly. Reading it
    /// registers nothing on the store itself: the box is created idle and filled on the next refresh, which runs
    /// outside any view's body.
    func rowActivity(for documentId: String) -> RowActivityBox {
        if let box = rowActivityBoxes[documentId]?.box { return box }
        let box = RowActivityBox()
        rowActivityBoxes[documentId] = RowActivityBox.Weak(box: box)
        scheduleRowActivityRefresh()
        return box
    }

    /// Recompute every box once, after the current burst of changes: a change-stream batch can bump `revision` and
    /// assign the listing in one turn.
    func scheduleRowActivityRefresh() {
        guard !rowActivityRefreshScheduled, !rowActivityBoxes.isEmpty else { return }
        rowActivityRefreshScheduled = true
        Task { @MainActor [weak self] in
            self?.refreshRowActivity()
        }
    }

    /// Each box takes its document's inputs now; a box whose value did not change is not written, so its row is not
    /// re-rendered.
    func refreshRowActivity() {
        rowActivityRefreshScheduled = false
        rowActivityBoxes = rowActivityBoxes.filter { $0.value.box != nil }
        for (documentId, held) in rowActivityBoxes {
            guard let box = held.box else { continue }
            let counts = childActivityCounts(of: documentId)
            box.set(.init(isSelfProcessing: isDocumentBusy(documentId), busyChildren: counts.busy,
                          totalChildren: counts.total))
        }
    }
}
