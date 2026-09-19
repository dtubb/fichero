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
    /// it to the detail model; `ActivityLogView` genuinely needs the whole
    /// `SelectedActivityRun` (`.isLive`, `.workflowId`, `.threadId` all
    /// matter to it), so that case carries the struct. `Hashable` so the
    /// Reader's dispatcher can key a mount on it (`.id(subject)`) — a
    /// long-lived pane must remount, not silently keep showing the PREVIOUS
    /// subject's rows under the new title.
    enum ReaderSubject: Hashable {
        case schedule(scheduleId: String)
        case trigger(triggerId: String)
        case activityRun(SelectedActivityRun)

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
    ///     call site as `workflowCanvasSelection(...) != nil` (#4882, spec
    ///     workflows.selection.library-row-opens-editor) — so Preview
    ///     (which reads that function directly, not this cell) and Reader
    ///     (which reads THIS cell) can never disagree about which surface a
    ///     workflow-node selection gets. `mode == .workflow(_)` already
    ///     takes the `.workflow` row below regardless of this flag — it
    ///     only matters while `mode == .library`.
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

/// One named rendition a pane can show. Ten cases, naming every rendition the
/// migration's Rulings inventory (spec `modes-to-panes.md`) identifies.
/// #4705 increment 1 wired six of them (`libraryBrowser`, `documentPreview`,
/// `documentReader`, `documentInspector`, `chatScope`, `workflowInspector`);
/// increment 2 wired `workflowCanvas`/`workflowRecipe`; increment 4a wires
/// `nodeDetail`. `entityInspector` (a future entity-inspector program)
/// stays declared-but-unassigned — see its doc comment.
/// `PaneContentPlanTests` pins that it does not appear yet, so a later
/// increment's diff reads as "this value changed" rather than landing
/// silently.
enum PaneSurface: String, CaseIterable, Equatable {
    /// The Library pane's one rendition: the navigator (tree/table). The
    /// matrix's `library` column is this constant for EVERY row (below) —
    /// the ruling this migration exists to make real, not today's literal
    /// truth for the remaining takeover rows (see `stablePanePlan`'s comment).
    case libraryBrowser
    /// A selected document, rendered in Source/Preview via `EditorView` —
    /// the fallback for every mode whose Preview cell has *something* to
    /// show but no rendition of its own yet (increment 4 replaces this for
    /// the remaining node-detail rows).
    case documentPreview
    /// A workflow's canvas (`WorkflowEditor`) in Source/Preview (#4705
    /// increment 2). At most ONE `WorkflowEditor` may be mounted per
    /// workflow — see `allowsSplit` below.
    case workflowCanvas
    /// A schedule/trigger/chain/batches/activity node's detail in
    /// Source/Preview (#4705 increment 4a) — `ScheduleDetailView`/
    /// `TriggerDetailView`/`ChainEditorView`/`BatchRunView`/`ActivityDetailView`,
    /// reused as-is. None of them holds a shared window-level binding the way
    /// `WorkflowEditor`'s `$editingWorkflow` did (each takes a plain value
    /// param + its own `@State`), so `allowsSplit` stays `true` — no
    /// per-surface split gate needed here.
    case nodeDetail
    /// A selected document, rendered in the Reader.
    case documentReader
    /// A workflow's run log (`WorkflowOutputLog`) in the Reader (#4705
    /// increment 2, spec Q2's answer — a workflow has no transcript but it
    /// does have a readable run history), replacing the old "Workflows Have
    /// No Transcript" dead end.
    case workflowRecipe
    /// A schedule's/trigger's/activity run's history in the Reader (#4705
    /// "4b-2", #4741) — `ScheduleRunHistoryView`/`TriggerRunHistoryView`/
    /// `ActivityLogView`, the SAME components the Preview `.nodeDetail` view
    /// already mounts (extracted so one renderer serves both panes). Needs
    /// the entity's identity, which `PaneSurface` deliberately does NOT
    /// carry (it stays a plain `CaseIterable` enum — Swift cannot synthesize
    /// `allCases` for a case with an associated value) — see `ReaderSubject`.
    case runHistory
    /// `DocumentInspector` — a document or entity-table selection today
    /// (see `entityInspector` below for the distinction).
    case documentInspector
    /// `WorkflowInspector` — already correct today (`Detail:384-390`).
    case workflowInspector
    /// `ChatInspector`'s Sources/Plan/Knowledge/Compare tabs — chat and
    /// comparison selections both route here today (`Detail:366`).
    case chatScope
    /// A dedicated entity-aware inspector surface, distinct from the plain
    /// `DocumentInspector` an entity-table row gets today. UNASSIGNED —
    /// reserved for `docs/contributor_manual/specs/ui/kg-entity-inspector.md`
    /// once that surface actually exists; `plan(for:entitySelection:)`
    /// deliberately ships `.documentInspector` now rather than guessing.
    case entityInspector

    /// Whether a pane showing this surface may be SPLIT into a second pane
    /// of the same kind. `false` only for `.workflowCanvas` (#4705
    /// increment 2): two `WorkflowEditor`s bound to the SAME
    /// `editingWorkflow` would run independent per-instance autosave tasks
    /// against one shared binding — a real write race
    /// (`WorkflowEditor.swift`'s `@State private var autosaveTask` vs. its
    /// `@Binding var editingWorkflow: Workflow`), not a hypothetical one.
    /// This only gates the split AFFORDANCE (the pane head's "+" menu); the
    /// render-time defense — never mounting a second editor even if a
    /// duplicate Preview leaf exists some other way — is
    /// `\.isSecondarySplitPane`, already computed per-leaf by
    /// `PaneList.secondaryLeafIDs()` and consumed in
    /// `widescreenCanvasPaneContent`.
    var allowsSplit: Bool {
        self != .workflowCanvas
    }
}

extension AppViewMode {
    /// #4705 "4b-2": the honest, KIND-SPECIFIC "nothing selected" sentence
    /// for the Reader's `.runHistory` dispatcher — `ReaderSubject.from(_:)`
    /// collapses `.schedule(nil)`/`.trigger(nil)`/`.activity(nil)` all to a
    /// bare `nil`, losing which kind it was, so the dispatcher needs this
    /// SEPARATE, kind-aware string instead of one generic sentence. `nil`
    /// for every mode whose reader cell isn't `.runHistory` in the first
    /// place (never read there).
    var runHistoryEmptyReason: String? {
        switch self {
        case .schedule: return "Select a schedule to see its run history."
        case .trigger: return "Select a trigger to see its run history."
        case .activity: return "Select a run to see its history."
        case .library, .chat, .comparison, .workflow, .chain, .batches, .automation:
            return nil
        }
    }

    /// The per-mode row of the #4525 matrix. A computed property so the
    /// exhaustive switch lives in the shape the repo already uses for
    /// per-mode routing (`ContentView.contentView`, `CompactShellPolicy`).
    ///
    /// The `library` cell is the constant `.surface(.libraryBrowser)` for
    /// EVERY row (#4705 increment 1) — this states the RULING ("the Library
    /// pane is always the navigator"), not always today's runtime truth: for
    /// the remaining takeover rows (`.comparison`, `.chain`, `.batches`,
    /// `.batch`, `.automation`, `.schedule`, `.trigger`, `.activity` —
    /// `.workflow` was fixed by increment 2, no longer a takeover) the
    /// Library pane today still shows a bespoke full-width view
    /// (`OntologyBrowser`, etc. — see `Nav`'s mode router). That was safe to
    /// state ahead of the code because nothing productive reads this cell
    /// (only `Detail:319,398` read `.preview`/`.inspector`, both only for
    /// `.emptyReason`) — increments 3-5 delete the remaining router branches
    /// to make it true at runtime too. Do not "fix" this constant back to
    /// matching a takeover; that would re-encode the bug the migration
    /// exists to remove.
    var stablePanePlan: PaneContentPlan.Plan {
        switch self {
        case .library:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                reader: .surface(.documentReader),
                inspector: .surface(.documentInspector)
            )
        case .chat:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                // Chat keeps Library + Source + Reader (modes-to-panes ruling):
                // the documents a conversation is about stay readable beside
                // it. This cell said `.empty` until 4b-1 made the Reader
                // actually consult it — enforcing that would have blanked the
                // Reader for every chat user.
                reader: .surface(.documentReader),
                inspector: .surface(.chatScope)
            )
        case .comparison:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                reader: .empty("A comparison has no reader view."),
                inspector: .surface(.chatScope)
            )
        case .workflow:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.workflowCanvas),
                // #4705 increment 2: the Reader shows the workflow's run log
                // (`WorkflowOutputLog`) instead of the old "Workflows Have No
                // Transcript" dead end — Q2's answer, a workflow has no
                // transcript but it does have a readable run history.
                reader: .surface(.workflowRecipe),
                inspector: .surface(.workflowInspector)
            )
        case .chain:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                // #4705 increment 4a: renders in Source/Preview now (the
                // "Create Chain" empty state moved there too, for a nil
                // chain — it's still an honest empty state, just relocated,
                // not deleted).
                preview: .surface(.nodeDetail),
                reader: .empty("A chain has no reader view."),
                // The old chain inspector showed WorkflowInspector bound to
                // whatever workflow was last edited — a stale surface, which
                // is worse than an honest absence (pane-audit 💀 cell).
                inspector: .empty("A chain has no inspector yet. Edit it on the canvas.")
            )
        case .batches:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.nodeDetail),
                reader: .empty("Batch runs have no reader view."),
                inspector: .empty("Select a batch run to see its details in Activity.")
            )
        // `.batch` DELETED (#4705 increment 4a) — see SidebarViewTypes.swift.
        case .automation:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .empty("Select a schedule or trigger in the sidebar."),
                reader: .empty("Automation has no reader view."),
                inspector: .empty("Select a schedule or trigger to inspect it.")
            )
        case .schedule:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.nodeDetail),
                // #4705 "4b-2" (#4741): run history in the Reader too, the
                // SAME `ScheduleRunHistoryView` the Preview detail view
                // mounts — `ReaderSubject.from(viewMode)` carries which
                // schedule; nil (nothing selected) is an honest empty
                // handled by the Reader's dispatcher, not this cell.
                reader: .surface(.runHistory),
                inspector: .empty("A schedule is edited in its detail view.")
            )
        case .trigger:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.nodeDetail),
                // #4705 "4b-2" — see `.schedule`.
                reader: .surface(.runHistory),
                inspector: .empty("A trigger is edited in its detail view.")
            )
        case .activity:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                // #4705 increment 4a: `ActivityDetailView` (already used by
                // the compact flow and its own window) renders here instead
                // of launching a separate window via the now-deleted
                // `ActivityWindowLauncherView`.
                preview: .surface(.nodeDetail),
                // #4705 "4b-2" — the SAME `ActivityLogView` the Preview
                // detail view's Log tab already mounts; no extraction was
                // needed, it was already a standalone component.
                reader: .surface(.runHistory),
                inspector: .empty("Run details live in the Activity window (Window menu, ⌥⌘A).")
            )
        }
    }
}

/// The ONE empty-state view every pane shares (#4525/#4518). SwiftUI's native
/// affordance, already used in-tree, so an honest absence looks the same in
/// every pane instead of four hand-rolled variants drifting.
struct PaneEmptyStateView: View {
    let reason: String
    var systemImage: String = "rectangle.dashed"

    var body: some View {
        ContentUnavailableView {
            Label("Nothing to Show", systemImage: systemImage)
        } description: {
            Text(reason)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
