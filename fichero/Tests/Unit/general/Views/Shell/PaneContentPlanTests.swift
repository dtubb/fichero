@testable import Fichero
import Foundation
import Testing

/// #4525: the pane matrix, asserted over EVERY `AppViewMode` × 4 panes.
///
/// The policy under test: a pane is `.surface(_)` or `.empty(reason)` — there
/// is no cell that unmounts, and every empty reason is a real sentence about
/// the actual situation. The switch in `stablePanePlan` is exhaustive, so a
/// new `AppViewMode` case fails to COMPILE until its row is decided; this
/// suite makes the decided row honest.
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
        // `.batch` DELETED (#4705 increment 4a) — see SidebarViewTypes.swift.
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

    @Test("every mode decides all four panes: a named surface, or an honest non-empty reason")
    func everyCellIsASurfaceOrAReason() {
        for (name, mode) in Self.everyMode {
            let plan = PaneContentPlan.plan(for: mode)
            for (pane, cell) in cells(plan) {
                switch cell {
                case .surface:
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

    @Test("the library COLUMN is always the .libraryBrowser surface — it is the spine")
    func theLibraryColumnIsAlwaysTheBrowser() {
        for (name, mode) in Self.everyMode {
            #expect(
                PaneContentPlan.plan(for: mode).library == .surface(.libraryBrowser),
                "\(name): the library column must stay the navigator surface"
            )
        }
    }

    @Test("a plain library selection names every pane's real surface")
    func librarySelectionNamesEverySurface() {
        let plan = PaneContentPlan.plan(for: .library(nil))
        #expect(plan == PaneContentPlan.Plan(
            library: .surface(.libraryBrowser),
            preview: .surface(.documentPreview),
            reader: .surface(.documentReader),
            inspector: .surface(.documentInspector)
        ))
    }

    @Test("the entities browser keeps the panes mounted with honest empties")
    func entitySelectionKeepsPanesMounted() {
        let plan = PaneContentPlan.plan(for: .library(nil), entitySelection: true)
        #expect(plan.library == .surface(.libraryBrowser))
        #expect(plan.preview.emptyReason != nil, "entities have no preview, said honestly")
        #expect(plan.reader.emptyReason != nil)
        #expect(plan.inspector == .surface(.documentInspector), "the KG inspector is real content")
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

    /// The mode surfaces that have no dedicated rendition yet render in the
    /// PREVIEW slot as `.documentPreview` — chat and comparison are the only
    /// two left there. `.workflow` is EXCLUDED (its own `.workflowCanvas`,
    /// see `workflowUsesItsOwnPreviewAndReaderSurfaces`); chain/schedule/
    /// trigger/activity/batches are EXCLUDED (their own `.nodeDetail`, see
    /// `nodeDetailModesLandInThePreviewSlot` — #4705 increment 4a).
    @Test("modes with no dedicated rendition get the generic document-preview cell")
    func modeSurfacesLandInThePreviewSlot() {
        let surfaced: [(String, AppViewMode)] = [
            ("chat", .chat(nil)), ("comparison", .comparison(nil)),
        ]
        for (name, mode) in surfaced {
            #expect(
                PaneContentPlan.plan(for: mode).preview == .surface(.documentPreview),
                "\(name): its surface belongs in the preview slot"
            )
        }
        // The one that genuinely has nothing to show says so instead.
        #expect(PaneContentPlan.plan(for: .automation).preview.emptyReason != nil)
    }

    /// #4803 / 4b-1: once the Reader obeys its plan cell, a wrong cell is a
    /// visible regression. Chat keeps its Reader — the documents a
    /// conversation is about stay readable beside it.
    @Test("chat keeps a document-driven Reader")
    func chatKeepsADocumentDrivenReader() {
        let cell = PaneContentPlan.plan(for: .chat(nil)).reader
        #expect(cell == .surface(.documentReader))
        #expect(cell.readerPageRoute == .documentDriven)
    }

    /// #4705 increment 4a: schedule/trigger/chain/batches/activity all
    /// render their existing detail view directly in Source/Preview
    /// (`.nodeDetail`) — the Library pane stays the plain navigator beside
    /// them, matching `.workflow`'s increment-2 shape. `.automation` (nothing
    /// selected) is EXCLUDED — it stays an honest empty, matching
    /// `.workflow(nil)`'s regular-width "just leave the Library showing"
    /// rule; there is no automation NODE to detail with nothing chosen.
    @Test("schedule/trigger/chain/batches/activity land on the node-detail surface")
    func nodeDetailModesLandInThePreviewSlot() {
        let nodeDetailModes: [(String, AppViewMode)] = [
            ("schedule", .schedule(nil)), ("trigger", .trigger(nil)),
            ("chain", .chain(nil)), ("batches", .batches),
            ("activity", .activity(nil)),
        ]
        for (name, mode) in nodeDetailModes {
            #expect(
                PaneContentPlan.plan(for: mode).preview == .surface(.nodeDetail),
                "\(name): its surface belongs in the node-detail slot"
            )
        }
    }

    /// #4705 increment 2 (`m2p.workflow-canvas-in-preview`,
    /// `m2p.workflow-reader-is-run-log`): a workflow selection's canvas
    /// lives in Source/Preview and its run log lives in the Reader — the
    /// Library pane stays the plain navigator beside them, and the
    /// inspector is unchanged (`WorkflowInspector`, already `[OK]`).
    @Test("a workflow selection names the canvas and run-log surfaces")
    func workflowUsesItsOwnPreviewAndReaderSurfaces() {
        let plan = PaneContentPlan.plan(for: .workflow(nil))
        #expect(plan == PaneContentPlan.Plan(
            library: .surface(.libraryBrowser),
            preview: .surface(.workflowCanvas),
            reader: .surface(.workflowRecipe),
            inspector: .surface(.workflowInspector)
        ))
    }

    /// The stale-surface cell from the pane audit: a chain must not show a
    /// WorkflowInspector bound to whatever workflow was last edited.
    @Test("a chain's inspector is an honest absence, not a stale workflow")
    func chainInspectorIsHonest() {
        #expect(PaneContentPlan.plan(for: .chain(nil)).inspector.emptyReason != nil)
    }

    /// #4705 increments only NAME the surfaces the CURRENT increment wires.
    /// `.entityInspector` (a future entity-inspector program) must not
    /// appear in the matrix yet — pinning its absence makes that later
    /// increment's diff legible as "this value changed" instead of landing
    /// silently inside this one. (`.nodeDetail` was the increment-4a
    /// version of this pin; it's wired now, so it moved to its own positive
    /// assertions above instead of staying in this negative one.)
    @Test("increments do not jump ahead to a future entity-inspector surface")
    func doesNotUseFutureSurfacesYet() {
        let notYetWired: Set<PaneSurface> = [.entityInspector]
        for (name, mode) in Self.everyMode {
            let plan = PaneContentPlan.plan(for: mode)
            for (pane, cell) in cells(plan) {
                if case .surface(let surface) = cell {
                    #expect(
                        !notYetWired.contains(surface),
                        "\(name).\(pane) uses \(surface), which is not wired yet"
                    )
                }
            }
        }
        // Also true of the entity-selection branch.
        let entityPlan = PaneContentPlan.plan(for: .library(nil), entitySelection: true)
        for (pane, cell) in cells(entityPlan) {
            if case .surface(let surface) = cell {
                #expect(
                    !notYetWired.contains(surface),
                    "entitySelection.\(pane) uses \(surface), which is not wired yet"
                )
            }
        }
    }

    // MARK: - Missing-preview-pane affordance (#4705 "4a-follow", `m2p.open-affordance-adds-missing-preview-pane`)

    /// Every `AppViewMode` × `hasPreviewLeaf`: the affordance fires only for
    /// the six node kinds whose Preview cell is `.workflowCanvas` or
    /// `.nodeDetail` AND no Preview leaf is already showing. A plain
    /// document/chat/comparison selection (`.documentPreview`/`.chatScope`)
    /// never triggers it — hiding Preview there is the user's own layout
    /// choice, not a takeover this migration retires.
    @Test("the missing-preview affordance fires only for the six node kinds, only when Preview is absent")
    func missingPreviewSurfaceFiresOnlyForNodeKindsWithoutAPreviewLeaf() {
        let nodeKindSurfaces: [String: PaneSurface] = [
            "workflow": .workflowCanvas,
            "chain": .nodeDetail, "batches": .nodeDetail, "schedule": .nodeDetail,
            "trigger": .nodeDetail, "activity": .nodeDetail,
        ]
        for (name, mode) in Self.everyMode {
            for hasPreviewLeaf in [true, false] {
                let result = PaneContentPlan.missingPreviewSurface(for: mode, hasPreviewLeaf: hasPreviewLeaf)
                if let expectedSurface = nodeKindSurfaces[name], !hasPreviewLeaf {
                    #expect(
                        result == expectedSurface,
                        "\(name), hasPreviewLeaf=false: expected \(expectedSurface)"
                    )
                } else {
                    #expect(
                        result == nil,
                        "\(name), hasPreviewLeaf=\(hasPreviewLeaf): expected no affordance"
                    )
                }
            }
        }
    }

    // MARK: - Reader-page routing (#4705 "4b-1", `m2p.reader-consults-the-plan`, #4803)

    /// Every `PaneSurface` (wrapped in `.surface`) + a representative `.empty`
    /// case: `.documentReader`/`.workflowRecipe` are the ONLY two surfaces the
    /// Reader's existing `effectiveDocument`-driven chain is verified
    /// against — everything else must come back `.unmounted`, never silently
    /// routed through code that was never proven to handle it.
    @Test("readerPageRoute recognizes only documentReader/workflowRecipe as document-driven")
    func readerPageRouteRecognizesOnlyTheTwoDocumentDrivenSurfaces() {
        let documentDrivenSurfaces: Set<PaneSurface> = [.documentReader, .workflowRecipe]
        for surface in PaneSurface.allCases {
            let cell = PaneContentPlan.Cell.surface(surface)
            if documentDrivenSurfaces.contains(surface) {
                #expect(cell.readerPageRoute == .documentDriven, "\(surface)")
            } else {
                #expect(cell.readerPageRoute == .unmounted(surface), "\(surface)")
            }
        }
        #expect(
            PaneContentPlan.Cell.empty("A schedule has no reader view.").readerPageRoute
                == .empty("A schedule has no reader view.")
        )
    }

    // MARK: - Split policy (#4705 increment 2)

    /// The pure split-affordance gate `PaneHead`/`ContentView+PreviewPaneHead`
    /// consume: `.workflowCanvas` is the ONLY surface that refuses a split —
    /// two `WorkflowEditor`s bound to the same `editingWorkflow` would run
    /// independent autosave tasks against one binding.
    @Test("only the workflow canvas refuses a split")
    func onlyWorkflowCanvasRefusesSplit() {
        for surface in PaneSurface.allCases {
            let expected = surface != .workflowCanvas
            #expect(
                surface.allowsSplit == expected,
                "\(surface).allowsSplit should be \(expected)"
            )
        }
    }
}
