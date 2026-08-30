@testable import Fichero
import Foundation
import Testing

/// #4525: the pane matrix, asserted over EVERY `AppViewMode` × 4 panes.
///
/// The policy under test: a pane is `.content` or `.empty(reason)` — there is
/// no cell that unmounts, and every empty reason is a real sentence about the
/// actual situation. The switch in `stablePanePlan` is exhaustive, so a new
/// `AppViewMode` case fails to COMPILE until its row is decided; this suite
/// makes the decided row honest.
@MainActor
struct PaneContentPlanTests {

    /// One representative instance per `AppViewMode` case — the enum has
    /// associated values, so exhaustiveness is owned by the compiler at the
    /// switch and this list only needs one row each. If a case is added, the
    /// switch fails to compile first; add its instance here second.
    private static let everyMode: [(String, AppViewMode)] = [
        ("library", .library(nil)),
        ("chat", .chat(nil)),
        ("comparison", .comparison(nil)),
        ("workflow", .workflow(nil)),
        ("chain", .chain(nil)),
        ("batches", .batches),
        ("batch", .batch(nil)),
        ("automation", .automation),
        ("schedule", .schedule(nil)),
        ("trigger", .trigger(nil)),
        ("activity", .activity(nil)),
    ]

    private func cells(_ plan: PaneContentPlan.Plan) -> [(String, PaneContentPlan.Cell)] {
        [
            ("library", plan.library),
            ("preview", plan.preview),
            ("reader", plan.reader),
            ("inspector", plan.inspector),
        ]
    }

    @Test("every mode decides all four panes: content, or an honest non-empty reason")
    func everyCellIsContentOrAReason() {
        for (name, mode) in Self.everyMode {
            let plan = PaneContentPlan.plan(for: mode)
            for (pane, cell) in cells(plan) {
                switch cell {
                case .content:
                    break
                case .empty(let reason):
                    #expect(
                        !reason.trimmingCharacters(in: .whitespaces).isEmpty,
                        "\(name).\(pane) has an empty reason string"
                    )
                }
            }
        }
    }

    @Test("the library COLUMN never goes empty for a node type — it is the spine")
    func theLibraryColumnIsAlwaysContent() {
        for (name, mode) in Self.everyMode {
            #expect(
                PaneContentPlan.plan(for: mode).library == .content,
                "\(name): the library column must stay mounted with content"
            )
        }
    }

    @Test("a plain library selection fills all four panes")
    func librarySelectionIsAllContent() {
        let plan = PaneContentPlan.plan(for: .library(nil))
        #expect(plan == PaneContentPlan.Plan(
            library: .content, preview: .content, reader: .content, inspector: .content
        ))
    }

    @Test("the entities browser keeps the panes mounted with honest empties")
    func entitySelectionKeepsPanesMounted() {
        let plan = PaneContentPlan.plan(for: .library(nil), entitySelection: true)
        #expect(plan.library == .content)
        #expect(plan.preview.emptyReason != nil, "entities have no preview, said honestly")
        #expect(plan.reader.emptyReason != nil)
        #expect(plan.inspector == .content, "the KG inspector is real content")
    }

    /// #4518 rides the same plan: with no library at all, every pane says so —
    /// the reason names the situation, not a per-pane guess like "Preview
    /// unavailable" + Retry against a closed library.
    @Test("no library open wins over every node-type cell")
    func noLibraryWinsEverywhere() {
        for (name, mode) in Self.everyMode {
            let plan = PaneContentPlan.plan(for: mode, hasLibrary: false)
            for (pane, cell) in cells(plan) {
                let reason = cell.emptyReason
                #expect(reason != nil, "\(name).\(pane) must be empty with no library")
                #expect(
                    reason?.contains("No library is open") == true,
                    "\(name).\(pane) must name the actual situation"
                )
            }
        }
    }

    /// The mode surfaces that exist render in the PREVIEW slot per the #4525
    /// target shape — chat, comparison, workflow, chain, schedule, trigger,
    /// activity and batches all have a real surface to show there.
    @Test("modes with a real surface get a content preview cell")
    func modeSurfacesLandInThePreviewSlot() {
        let surfaced: [(String, AppViewMode)] = [
            ("chat", .chat(nil)), ("comparison", .comparison(nil)),
            ("workflow", .workflow(nil)), ("chain", .chain(nil)),
            ("schedule", .schedule(nil)), ("trigger", .trigger(nil)),
            ("activity", .activity(nil)), ("batches", .batches),
        ]
        for (name, mode) in surfaced {
            #expect(
                PaneContentPlan.plan(for: mode).preview == .content,
                "\(name): its surface belongs in the preview slot"
            )
        }
        // The two that genuinely have nothing to show say so instead.
        #expect(PaneContentPlan.plan(for: .batch(nil)).preview.emptyReason != nil)
        #expect(PaneContentPlan.plan(for: .automation).preview.emptyReason != nil)
    }

    /// The stale-surface cell from the pane audit: a chain must not show a
    /// WorkflowInspector bound to whatever workflow was last edited.
    @Test("a chain's inspector is an honest absence, not a stale workflow")
    func chainInspectorIsHonest() {
        #expect(PaneContentPlan.plan(for: .chain(nil)).inspector.emptyReason != nil)
    }
}
