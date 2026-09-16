import SwiftUI

/// The two domain menus from the menus-and-commands spec — **Read** and
/// **Knowledge** — composed as ONE `Commands` element so the app's
/// `@CommandsBuilder` stays under its 10-entry arity cap (#3347, the same
/// reason `GoMenuCommands` / `FormatMenuCommands` are single composed
/// elements). It replaces the former `CommandMenu("Data")` slot, so the two
/// menus land in the bar right after **Go**, in the spec's order
/// (`… View · Go · Read · Knowledge · …`).
///
/// Both menus render the SAME shared `Focused*Button` / `*Section` components
/// the toolbar and View menu use — no hand-rolled twins (spec: "one source,
/// many surfaces"). Every verb self-disables via `@FocusedValue` when no
/// window publishes it, exactly as the View-menu sections do.
struct ReadKnowledgeMenuCommands: Commands {
    private let featureManager = FeatureManager.shared

    var body: some Commands {
        // MARK: Read — the reading & annotating surface (spec Part IV/VI).
        // Everything you do WHILE reading a source lives here, not scattered
        // in View: the reader lens and the zoom / magnifier / loupe controls.
        CommandMenu("Read") {
            Menu("Reader Lens") {
                ReaderLensSection()
            }

            // ImagePreviewMenuCommands is itself a "Zoom" flyout carrying the
            // magnifier + loupe controls — reused unchanged (keeps its ⌘0/⌘9/
            // ⌘±/⌘⇧M/⌘⌥L shortcuts on the leaf items).
            ImagePreviewMenuCommands()
        }

        // MARK: Knowledge — making & querying meaning (spec Part VII/VIII).
        // This is the former "Data" menu, renamed and organized into flyouts.
        CommandMenu("Knowledge") {
            // New Folder + Import stay here for now (they were in "Data"); the
            // spec's eventual home for them is File ▸ Import, deferred to keep
            // this change to menu re-homing without touching File's arity-
            // capped body.
            FocusedNewFolderButton()

            FocusedImportFilesButton()

            Divider()

            // The global Knowledge-Graph view-mode switcher
            // (List/Graph/Chart/Timeline/Map) — the spec's "Knowledge Graph
            // View" item. Reused from the View menu unchanged.
            KnowledgeGraphViewModeSection()

            // Workflows ▸ — the creation verbs + Run Workflow on Selection,
            // each self-gated exactly as the former Data menu gated them.
            if featureManager.isWorkflowsEnabled
                || featureManager.allFeaturesEffectivelyEnabled
                || featureManager.isAutomationEnabled
                || featureManager.isWorkflowRunOnSelectionEnabled {
                Divider()

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
}
