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
    @Environment(\.openWindow) private var openWindow

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
            // New Folder + Import moved to File ▸ Import (CD 2026-09-16,
            // menus-and-commands spec) — getting things in/out is File's job,
            // not Knowledge's.

            // The "Knowledge Graph View" item (List/Graph/Chart/Timeline/Map
            // switcher for the KG sidebar mode's OntologyBrowser) DELETED
            // (#4705 increment 3, creative director 2026-09-18): the KG
            // sidebar mode retires; entity/claim browsing lives in the
            // library-wide Entities/Claims tables, which have no equivalent
            // mode switcher to offer here.

            // The W3C SPARQL query console (#3298) — recovered into its own
            // window (#4705 increment 3, CD 2026-06-25 ruling #2593/#2614:
            // "SPARQL is wanted and must be made VISIBLE; never delete it")
            // when the KG sidebar mode that used to host it as a sheet
            // retired. No keyboard shortcut — a query console is not a
            // muscle-memory verb.
            Button("SPARQL Console…") {
                openWindow(id: "sparql-console")
            }

            Divider()

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
