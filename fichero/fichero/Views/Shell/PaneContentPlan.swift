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
/// `PaneContentPlanTests` matrix then asserts every cell is `.content` or
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
        /// The pane renders its real surface for this mode.
        case content
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
                library: .content,
                preview: .empty("An entity list has no preview. Select a document to preview it."),
                reader: .empty("An entity list has no reader view."),
                inspector: .content
            )
        }
        return mode.stablePanePlan
    }
}

extension AppViewMode {
    /// The per-mode row of the #4525 matrix. A computed property so the
    /// exhaustive switch lives in the shape the repo already uses for
    /// per-mode routing (`ContentView.contentView`, `CompactShellPolicy`).
    var stablePanePlan: PaneContentPlan.Plan {
        switch self {
        case .library:
            return PaneContentPlan.Plan(
                library: .content, preview: .content, reader: .content, inspector: .content
            )
        case .chat:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("A conversation has no reader view."),
                inspector: .content
            )
        case .comparison:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("A comparison has no reader view."),
                inspector: .content
            )
        case .workflow:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("A workflow has no reader view."),
                inspector: .content
            )
        case .chain:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("A chain has no reader view."),
                // The old chain inspector showed WorkflowInspector bound to
                // whatever workflow was last edited — a stale surface, which
                // is worse than an honest absence (pane-audit 💀 cell).
                inspector: .empty("A chain has no inspector yet. Edit it on the canvas.")
            )
        case .batches:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("Batch runs have no reader view."),
                inspector: .empty("Select a batch run to see its details in Activity.")
            )
        case .batch:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .empty("Batch monitoring is unified under Activity."),
                reader: .empty("Batch monitoring is unified under Activity."),
                inspector: .empty("Batch monitoring is unified under Activity.")
            )
        case .automation:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .empty("Select a schedule or trigger in the sidebar."),
                reader: .empty("Automation has no reader view."),
                inspector: .empty("Select a schedule or trigger to inspect it.")
            )
        case .schedule:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("A schedule has no reader view."),
                inspector: .empty("A schedule is edited in its detail view.")
            )
        case .trigger:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
                reader: .empty("A trigger has no reader view."),
                inspector: .empty("A trigger is edited in its detail view.")
            )
        case .activity:
            return PaneContentPlan.Plan(
                library: .content,
                preview: .content,
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
