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
    }

    /// The four #4525 surfaces. Preview, Reader and Inspector remain three
    /// distinct surfaces — hard rule; this type must never merge them.
    struct Plan: Equatable {
        let library: Cell
        let preview: Cell
        let reader: Cell
        let inspector: Cell
    }

    /// The matrix entry point.
    ///
    /// - Parameters:
    ///   - mode: the selection's view mode (the ONE axis, per the V7 fix —
    ///     every sidebar selection sets it).
    ///   - entitySelection: the library's entities browser is selected.
    ///   - hasLibrary: false when the window has no library at all (#4518);
    ///     wins over every node-type cell.
    static func plan(
        for mode: AppViewMode,
        entitySelection: Bool = false,
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
        return mode.stablePanePlan
    }
}

/// One named rendition a pane can show. Ten cases (#4705 increment 1),
/// naming every rendition the migration's Rulings inventory (spec
/// `modes-to-panes.md`) identifies — but only SIX are wired to a matrix cell
/// below yet (`libraryBrowser`, `documentPreview`, `documentReader`,
/// `documentInspector`, `chatScope`, `workflowInspector`): the other four
/// (`workflowCanvas`, `nodeDetail`, `workflowRecipe`, `entityInspector`) stay
/// declared-but-unassigned until the increment that gives them a real
/// rendition (2, 4, 2, and a future entity-inspector program respectively) —
/// see each case's doc comment. `PaneContentPlanTests` pins that these four
/// do not appear yet, so a later increment's diff reads as "this value
/// changed" rather than landing silently.
enum PaneSurface: String, CaseIterable, Equatable {
    /// The Library pane's one rendition: the navigator (tree/table). The
    /// matrix's `library` column is this constant for EVERY row (below) —
    /// the ruling this migration exists to make real, not today's literal
    /// truth for the takeover rows (see `stablePanePlan`'s comment).
    case libraryBrowser
    /// A selected document, rendered in Source/Preview via `EditorView` —
    /// today's fallback for every mode whose Preview cell has *something*
    /// to show, since the Mac Preview pane does not yet branch on
    /// `viewMode` (increments 2/4 replace this per-mode).
    case documentPreview
    /// A workflow's canvas (`WorkflowEditor`) in Source/Preview. UNASSIGNED
    /// until increment 2 moves it out of the Library-pane takeover.
    case workflowCanvas
    /// A schedule/trigger/chain/batch/activity run's detail in
    /// Source/Preview. UNASSIGNED until increment 4.
    case nodeDetail
    /// A selected document, rendered in the Reader.
    case documentReader
    /// A workflow's readable recipe/run-log in the Reader (spec's Q2 —
    /// "what does the Reader show for a workflow"). UNASSIGNED until
    /// increment 2.
    case workflowRecipe
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
}

extension AppViewMode {
    /// The per-mode row of the #4525 matrix. A computed property so the
    /// exhaustive switch lives in the shape the repo already uses for
    /// per-mode routing (`ContentView.contentView`, `CompactShellPolicy`).
    ///
    /// The `library` cell is the constant `.surface(.libraryBrowser)` for
    /// EVERY row (#4705 increment 1) — this states the RULING ("the Library
    /// pane is always the navigator"), not always today's runtime truth: for
    /// the takeover rows (`.workflow`, `.comparison`, `.chain`, `.batches`,
    /// `.batch`, `.automation`, `.schedule`, `.trigger`, `.activity`) the
    /// Library pane today actually shows a bespoke full-width view
    /// (`WorkflowEditor`, `OntologyBrowser`, etc. — see `Nav`'s mode router).
    /// That is safe to state now because nothing productive reads this cell
    /// yet (only `Detail:319,398` read `.preview`/`.inspector`, both only for
    /// `.emptyReason`) — increments 2-5 delete the router branches to make it
    /// true at runtime too. Do not "fix" this constant back to matching
    /// today's takeover; that would re-encode the bug the migration exists
    /// to remove.
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
                reader: .empty("A conversation has no reader view."),
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
                preview: .surface(.documentPreview),
                reader: .empty("A workflow has no reader view."),
                inspector: .surface(.workflowInspector)
            )
        case .chain:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                reader: .empty("A chain has no reader view."),
                // The old chain inspector showed WorkflowInspector bound to
                // whatever workflow was last edited — a stale surface, which
                // is worse than an honest absence (pane-audit 💀 cell).
                inspector: .empty("A chain has no inspector yet. Edit it on the canvas.")
            )
        case .batches:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                reader: .empty("Batch runs have no reader view."),
                inspector: .empty("Select a batch run to see its details in Activity.")
            )
        case .batch:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .empty("Batch monitoring is unified under Activity."),
                reader: .empty("Batch monitoring is unified under Activity."),
                inspector: .empty("Batch monitoring is unified under Activity.")
            )
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
                preview: .surface(.documentPreview),
                reader: .empty("A schedule has no reader view."),
                inspector: .empty("A schedule is edited in its detail view.")
            )
        case .trigger:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                reader: .empty("A trigger has no reader view."),
                inspector: .empty("A trigger is edited in its detail view.")
            )
        case .activity:
            return PaneContentPlan.Plan(
                library: .surface(.libraryBrowser),
                preview: .surface(.documentPreview),
                reader: .empty("A workflow run has no reader view."),
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
