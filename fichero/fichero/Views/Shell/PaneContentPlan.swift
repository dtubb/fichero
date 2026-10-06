import SwiftUI

// MARK: - The one place a (node-type × pane) cell is decided (#4525)

/// STABLE PANES: for every `AppViewMode`, each of the four panes — Library
/// column, Preview, Reader, Inspector — either renders its real surface or an
/// HONEST empty state naming why. Never a silent unmount, never a stale
/// surface from the previous selection.
///
/// Pure and exhaustive on purpose (the same trick as `CompactShellPolicy`,
/// #3009): the #4525 matrix IS the switch in `stablePanePlan`, and a new
/// `AppViewMode` case fails to compile until its four cells are decided. The
/// `PaneContentPlanTests` matrix then asserts every cell is `.surface(_)` or
/// `.empty(reason)` with a non-empty reason — a conditional that unmounts has
/// no representation here at all.
///
/// Sibling of `LibraryEmptyReason` (#4403), which owns "why does the library
/// BODY have no rows"; this type owns "what does each PANE show for this kind
/// of node". The #4518 "no library at all" case rides the same plan via
/// `hasLibrary` so the two defects share one mechanism (they were the same
/// defect from two sides).
enum PaneContentPlan {

    /// What one pane shows. There is no third case — that is the policy.
    enum Cell: Equatable {
        /// The pane renders a real, NAMED surface for this mode (#4705
        /// increment 1: `.content` grew a payload so the matrix can say
        /// WHICH rendition, not just that one exists).
        case surface(PaneSurface)
        /// The pane stays MOUNTED and says why it is empty, in user terms.
        case empty(String)

        var emptyReason: String? {
            if case .empty(let reason) = self { return reason }
            return nil
        }

        /// #4705 "4b-1"/"4b-2" (`m2p.reader-consults-the-plan`, #4803;
        /// `m2p.automation-run-history-in-reader`, #4741): which of the
        /// Reader's branches this cell selects, once the Reader actually asks
        /// the plan instead of routing off a resolved `Document` alone (the
        /// #4803 bug — a schedule/trigger/chain/batches/automation/activity
        /// selection used to leave the Reader showing whatever document was
        /// PREVIOUSLY open, because nothing cleared it and nothing consulted
        /// this cell). `.documentDriven` is the ONLY two surfaces the
        /// Reader's existing `effectiveDocument`/`doc.isWorkflowNode` chain is
        /// verified against; `.runHistory` is its own named route (needs
        /// `ReaderSubject`, not just this cell); a FOURTH surface reaching
        /// the Reader before its own mount exists is `.unmounted`, never
        /// silently routed through code that was never proven to handle it.
        var readerPageRoute: ReaderPageRoute {
            switch self {
            case .surface(.documentReader), .surface(.workflowRecipe):
                return .documentDriven
            case .surface(.runHistory):
                return .runHistory
            case .empty(let reason):
                return .empty(reason)
            case .surface(let other):
                return .unmounted(other)
            }
        }
    }

    /// #4705 "4b-1"/"4b-2": the four-way split `PaneContentPlan.Cell.
    /// readerPageRoute` resolves to. `.unmounted` deliberately keeps the
    /// surface it didn't recognize, so its placeholder can name what is
    /// missing instead of rendering a blank. `.runHistory` carries no
    /// payload itself — the Reader also reads `readerSubject: ReaderSubject?`
    /// (computed by the same host, from the same `viewMode`) to know WHICH
    /// schedule/trigger/run to show.
    enum ReaderPageRoute: Equatable {
        case documentDriven
        case runHistory
        case empty(String)
        case unmounted(PaneSurface)
    }

    /// #4705 "4b-2": the entity identity the Reader's `.runHistory` route
    /// needs, computed by the same host that computes `readerCell`
    /// (`PaneContentPlan.plan(for: viewMode).reader`) — from the SAME
    /// `viewMode`, so the two never disagree. Carries the SMALLEST thing
    /// each extracted component actually needs: `ScheduleRunHistoryView`/
    /// `TriggerRunHistoryView` only read an id string, so carrying the whole
    /// `ScheduleInfo`/`TriggerInfo` would make the Reader re-evaluate on
    /// every unrelated field change (next-run time, run count, …) and couple
    /// it to the detail model; `ActivityDetailsLogPane` needs the whole
    /// `ActivitySelection` (the row's job id and its project, #5561, both
    /// matter to it), so that case carries the struct. `Hashable` so the
    /// Reader's dispatcher can key a mount on it (`.id(subject)`) — a
    /// long-lived pane must remount, not silently keep showing the PREVIOUS
    /// subject's rows under the new title.
    enum ReaderSubject: Hashable {
        case schedule(scheduleId: String)
        case trigger(triggerId: String)
        case activityRun(ActivitySelection)

        /// Exhaustive over every `AppViewMode` case, no `default` — a new
        /// case fails to compile here until this function's answer for it is
        /// a considered decision, not a silent `nil`.
        static func from(_ viewMode: AppViewMode) -> ReaderSubject? {
            switch viewMode {
            case .schedule(let info):
                return info.map { .schedule(scheduleId: $0.scheduleId) }
            case .trigger(let info):
                return info.map { .trigger(triggerId: $0.triggerId) }
            case .activity(let run):
                return run.map { .activityRun($0) }
            case .library, .chat, .comparison, .workflow, .chain, .batches, .automation:
                return nil
            }
        }
    }

    /// The four #4525 surfaces. Preview, Reader and Inspector remain three
    /// distinct surfaces — hard rule; this type must never merge them.
    struct Plan: Equatable {
        let library: Cell
        let preview: Cell
        let reader: Cell
        let inspector: Cell
    }

    /// The Preview surface `mode` wants but the applied pane list does not
    /// currently show — nil when there is nothing to add. #4705 "4a-follow":
    /// the workflow ruling generalized ("an explicit Open affordance adds the
    /// pane; nothing moves automatically") to the five kinds 4a moved into
    /// Preview alongside the workflow canvas from increment 2.
    ///
    /// Scoped to `.workflowCanvas` and `.nodeDetail` ONLY — never
    /// `.documentPreview`/`.chatScope` — deliberately: a plain document or
    /// chat selection with Preview hidden is the user's own layout choice
    /// (a Reader-only workspace is legitimate), not a takeover this
    /// migration is retiring. Only the six node kinds whose Preview
    /// rendition has no OTHER home get the affordance.
    static func missingPreviewSurface(for mode: AppViewMode, hasPreviewLeaf: Bool) -> PaneSurface? {
        guard !hasPreviewLeaf else { return nil }
        guard case .surface(let surface) = mode.stablePanePlan.preview else { return nil }
        guard surface == .workflowCanvas || surface == .nodeDetail else { return nil }
        return surface
    }

    /// The matrix entry point.
    ///
    /// - Parameters:
    ///   - mode: the selection's view mode (the ONE axis, per the V7 fix —
    ///     every sidebar selection sets it).
    ///   - entitySelection: the library's entities browser is selected.
    ///   - workflowNodeSelected: a Library row's SINGLE selection is a
    ///     workflow mirror document, computed the SAME way at every real
    ///     call site as `ContentView.activeWorkflowItem != nil` (#4882, spec
    ///     workflows.selection.library-row-opens-editor) — so Preview
    ///     (which reads `activeWorkflowItem` directly, not this cell) and
    ///     Reader/Inspector (which read THIS cell) can never disagree about
    ///     which surface a workflow-node selection gets. `mode ==
    ///     .workflow(_)` already takes the `.workflow` row below regardless
    ///     of this flag — it only matters while `mode == .library`.
    ///   - hasLibrary: false when the window has no library at all (#4518);
    ///     wins over every node-type cell.
    static func plan(
        for mode: AppViewMode,
        entitySelection: Bool = false,
        workflowNodeSelected: Bool = false,
        hasLibrary: Bool = true
    ) -> Plan {
        guard hasLibrary else {
            let reason = "No library is open. Open a library to see its contents."
            return Plan(
                library: .empty(reason), preview: .empty(reason),
                reader: .empty(reason), inspector: .empty(reason)
            )
        }
        if entitySelection, case .library = mode {
            return Plan(
                library: .surface(.libraryBrowser),
                preview: .empty("An entity list has no preview. Select a document to preview it."),
                reader: .empty("An entity list has no reader view."),
                // Today's inspector for an entity-table selection is the
                // ordinary DocumentInspector (`inspectorView`'s `.library`
                // arm does not branch on `entitySelection`) — honest, not
                // yet the dedicated entity-aware surface `PaneSurface`
                // reserves as `.entityInspector` for when
                // `docs/contributor_manual/specs/ui/kg-entity-inspector.md`
                // lands a real one.
                inspector: .surface(.documentInspector)
            )
        }
        // #4882: a Library row's workflow-node selection gets the SAME three
        // cells the sidebar's `.workflow` mode gets (below, `stablePanePlan`)
        // — canvas in Preview, run log in Reader, `WorkflowInspector` in the
        // Inspector ("inspector tabs only for the selected kind" ruling) —
        // WITHOUT flipping `mode` itself. `mode == .workflow(_)` already
        // reaches the same three cells via `stablePanePlan` below, so this
        // guard only fires for the NEW case: `.library` with a workflow row
        // selected.
        if workflowNodeSelected, case .library = mode {
            return Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.workflowCanvas),
                reader: .surface(.workflowRecipe),
                inspector: .surface(.workflowInspector)
            )
        }
        return mode.stablePanePlan
    }
}
