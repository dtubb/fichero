import Foundation

/// What a container row shows while work is happening (#4417).
///
/// Running Catalogue on a PDF's pages spun the PDF too, and running it on a
/// folder's contents spun the folder. `folderHasBusyChild` promoted any busy
/// child into the parent's own spinner, so parent and child rendered the
/// identical indicator.
///
/// That is false — a container is not being processed, its contents are — and
/// it costs the one thing the parent could usefully say: **how far along its
/// children are.** It also makes the signal useless at a glance, because every
/// ancestor of every working document spins and none of the motion tells you
/// which rows are the actual subjects of the run.
///
/// The aggregation was right; the rendering was not. This keeps the aggregate
/// and gives it its own treatment.
///
/// **On the ambiguous case.** When a container's own status is `.processing`
/// *and* its children are busy, the client cannot distinguish "the engine
/// marked the parent because its children are working" from "the parent is
/// itself the subject of a stage". So busy children win: the aggregate is
/// strictly more informative than a second spinner, and the own-indicator is
/// reserved for a container processing with no busy children — which is
/// precisely the folder-level catalogue stage writing to the folder document
/// (#4404, #4414). Work on the container and work on its contents stay
/// distinguishable, which the multi-level cataloguing model (#4399) needs.
enum ContainerActivity: Equatable {
    /// Nothing to show.
    case idle
    /// This document is itself the subject of work — the leaf treatment.
    case own
    /// This document's CONTENTS are being worked on.
    case children(busy: Int, total: Int)

    /// - Parameters:
    ///   - isSelfProcessing: this document's own record says processing.
    ///   - busyChildren: direct children currently processing.
    ///   - totalChildren: direct children known to the client.
    static func resolve(
        isSelfProcessing: Bool,
        busyChildren: Int,
        totalChildren: Int
    ) -> ContainerActivity {
        if busyChildren > 0 {
            return .children(busy: busyChildren, total: max(totalChildren, busyChildren))
        }
        // No child is working, so a processing status can only be this
        // document's own. A container whose children have all finished lands
        // here with `isSelfProcessing == false` and goes idle immediately,
        // without waiting for anything else.
        return isSelfProcessing ? .own : .idle
    }

    /// Whether the row shows the per-item spinner. True only for `.own`: that
    /// is the whole point of the issue.
    var showsLeafSpinner: Bool { self == .own }

    /// Determinate fraction for the aggregate, or `nil` when there is nothing
    /// to be determinate about.
    ///
    /// Deliberately fraction-of-FINISHED, so a run that has not started reads
    /// as 0 and a nearly-done one reads as nearly full.
    var progress: Double? {
        guard case .children(let busy, let total) = self, total > 0 else { return nil }
        let done = max(0, total - busy)
        return min(1, max(0, Double(done) / Double(total)))
    }

    /// Short summary for the row's tooltip / accessibility label.
    ///
    /// Says what is happening to the CONTENTS, so it can never be read as the
    /// container itself being processed.
    var summary: String? {
        switch self {
        case .idle:
            return nil
        case .own:
            return "Processing"
        case .children(let busy, let total):
            let done = max(0, total - busy)
            return total > 0
                ? "Processing contents — \(done) of \(total) done"
                : "Processing \(busy) item\(busy == 1 ? "" : "s")"
        }
    }

    var isActive: Bool { self != .idle }
}
