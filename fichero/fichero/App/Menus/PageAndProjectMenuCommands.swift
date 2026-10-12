import SwiftUI

/// The domain menus from the menus-and-commands spec — **Page** and **Project** (ruled 2026-10-10:
/// Read became Page and the Segment menu folded into it, #5652 slice 2) — composed as ONE `Commands` element so the app's
/// `@CommandsBuilder` stays under its 10-entry arity cap (#3347, the same
/// reason `GoMenuCommands` / `FormatMenuCommands` are single composed
/// elements). They land in the bar right after **Go**. Project (ruled
/// 2026-10-10) replaced the Knowledge menu, which replaced the former
/// `CommandMenu("Data")`.
///
/// Every menu renders the SAME shared `Focused*Button` / `*Section` components
/// the toolbar and View menu use — no hand-rolled twins (spec: "one source,
/// many surfaces"). Every verb self-disables via `@FocusedValue` when no
/// window publishes it, exactly as the View-menu sections do.
struct PageAndProjectMenuCommands: Commands {
    private let featureManager = FeatureManager.shared
    @Environment(\.openWindow) private var openWindow

    var body: some Commands {
        // MARK: Page — the page in front of you (ruled 2026-10-10, was Read; #5652 slice 2).
        // Everything you do WHILE reading a page lives here, not scattered in View: the reader lens,
        // the doubtful words, the zoom / magnifier / loupe controls, rotate, and the page's segments
        // (the Segment menu folded in). Every item keeps its chord.
        CommandMenu("Page") {
            Menu("Reader Lens") {
                ReaderLensSection()
            }
            // Where the readers disagree (#5665): the doubtful words, one by one.
            DoubtfulWordMenuSection()

            // ImagePreviewMenuCommands is itself a "Zoom" flyout carrying the
            // magnifier + loupe controls — reused unchanged (keeps its ⌘0/⌘9/
            // ⌘±/⌘⇧M/⌘⌥L shortcuts on the leaf items).
            ImagePreviewMenuCommands()

            Divider()
            RotateImageMenuSection()

            // The page's segments, on the focused Preview's selection (#5229; was the Segment menu).
            Section("Segments") {
                SegmentMenuContent()
                // A line's and a segment's verbs on the focused list's selection (#5652 slice 4, group 3).
                Divider()
                FocusedLineVerbButtons()
            }
        }

        // MARK: Project — the recipe, stage by stage (ruled 2026-10-10, menus-and-commands spec).
        // Set Up… and Start first, then one titled section per recipe stage in recipe order
        // (`ProjectMenuStage`). The Knowledge menu retired into it: SPARQL Console… is Connect's,
        // and Workflows ▸ / Chat ▸ follow the stages.
        CommandMenu("Project") {
            FocusedSetUpButton()
            FocusedStartRecipeButton()

            ForEach(ProjectMenuStage.allCases) { stage in
                projectStageSection(stage)
            }

            Section("Activity") {
                FocusedActivityRunButtons()
            }

            Divider()
            projectWorkflowsAndChat
        }
    }

    /// One stage's section. Only verbs the app has are listed; a stage with none yet shows nothing
    /// (Structure is [GAP] in the spec). Read holds the recipe's run on one folder (#5540).
    @ViewBuilder
    private func projectStageSection(_ stage: ProjectMenuStage) -> some View {
        switch stage {
        case .read:
            Section(stage.title) {
                // Reading ▸: the reading verbs on the selection (#5652 slice 2).
                Menu("Reading") {
                    FocusedRunRecipeOnFolderButton()
                }
            }
        case .organise:
            Section(stage.title) {
                FocusedFindDocumentsButton()
            }
        case .connect:
            Section(stage.title) {
                // The W3C SPARQL query console (#3298), in its own window (CD 2026-06-25 ruling
                // #2593/#2614: "SPARQL is wanted and must be made VISIBLE; never delete it"). No
                // keyboard shortcut — a query console is not a muscle-memory verb.
                Button("SPARQL Console…") {
                    openWindow(id: "sparql-console")
                }
            }
        case .train:
            Section(stage.title) {
                FocusedTrainButtons()
            }
        case .structure:
            EmptyView()
        }
    }

    /// Workflows ▸ (the creation verbs + Run Workflow on Selection, each self-gated) and Chat ▸.
    @ViewBuilder
    private var projectWorkflowsAndChat: some View {
        if featureManager.isWorkflowsEnabled
            || featureManager.allFeaturesEffectivelyEnabled
            || featureManager.isAutomationEnabled
            || featureManager.isWorkflowRunOnSelectionEnabled {
            Menu("Workflows") {
                if featureManager.isWorkflowsEnabled {
                    FocusedNewWorkflowButton()
                }

                if featureManager.allFeaturesEffectivelyEnabled {
                    FocusedNewComparisonButton()
                    FocusedNewChainButton()
                }

                if featureManager.isAutomationEnabled {
                    Divider()
                    FocusedNewScheduleButton()
                }

                if featureManager.isWorkflowRunOnSelectionEnabled {
                    Divider()
                    FocusedRunWorkflowOnSelectionButton()
                }
            }
        }

        // Chat ▸ — New Chat, the same shared component the sidebar uses.
        if featureManager.isChatEnabled {
            Menu("Chat") {
                FocusedNewChatButton()
            }
        }
    }
}
