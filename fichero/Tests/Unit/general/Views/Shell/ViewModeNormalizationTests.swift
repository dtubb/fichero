@testable import Fichero
import Foundation
import Testing

/// #4705 increment 0: the stale-inspector "Chat Scope" leak. Selecting a
/// chat then switching the sidebar to Research (⌃⌘8) or Knowledge Graph
/// (⌃⌘9) used to leave `ChatInspector` on screen because `viewMode` was
/// deliberately left untouched for those two modes. This suite pins
/// `ViewModeNormalization.normalizedViewMode` over EVERY `SidebarMode` ×
/// `AppViewMode` pair, plus the specific regression.
@Suite("ViewModeNormalization")
struct ViewModeNormalizationTests {

    /// One representative instance per `AppViewMode` case (associated values
    /// mean full enumeration isn't possible; this mirrors the
    /// `PaneContentPlanTests.everyMode` pattern — a new `AppViewMode` case
    /// fails the exhaustive `switch` in `ViewModeNormalization` at compile
    /// time first, this table only needs one representative row).
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

    /// For every SidebarMode × AppViewMode pair, the normalized result must
    /// be a view mode `ViewModeNormalization.belongs` accepts for that
    /// sidebar mode — i.e. never a view mode belonging to a DIFFERENT
    /// mode's family. That is the general form of the "stale inspector"
    /// bug: normalizing must never leave (or produce) a view mode foreign
    /// to the new sidebar mode.
    @Test("normalized result always belongs to the new sidebar mode", arguments: SidebarMode.allCases)
    func normalizedResultBelongsToNewMode(sidebarMode: SidebarMode) {
        for (label, view) in Self.everyMode {
            let normalized = ViewModeNormalization.normalizedViewMode(
                current: view,
                forNewSidebarMode: sidebarMode
            )
            #expect(
                ViewModeNormalization.belongs(normalized, to: sidebarMode),
                "\(label) -> \(sidebarMode) produced a view mode that does not belong to the new sidebar mode"
            )
        }
    }

    // MARK: - Regression: the Chat Scope leak (#4705)

    @Test("a selected chat switching to Research no longer keeps a chat view mode")
    func chatToResearchDropsChatViewMode() {
        let normalized = ViewModeNormalization.normalizedViewMode(
            current: .chat(nil),
            forNewSidebarMode: .research
        )
        if case .chat = normalized {
            Issue.record("expected a non-chat view mode after switching to Research")
        }
        if case .comparison = normalized {
            Issue.record("expected a non-chat view mode after switching to Research")
        }
    }

    @Test("a selected chat switching to Knowledge Graph no longer keeps a chat view mode")
    func chatToKnowledgeGraphDropsChatViewMode() {
        let normalized = ViewModeNormalization.normalizedViewMode(
            current: .chat(nil),
            forNewSidebarMode: .knowledgeGraph
        )
        if case .chat = normalized {
            Issue.record("expected a non-chat view mode after switching to Knowledge Graph")
        }
        if case .comparison = normalized {
            Issue.record("expected a non-chat view mode after switching to Knowledge Graph")
        }
    }

    // MARK: - Pinned behaviour: unchanged from the pre-#4705 handleSidebarModeChange

    @Test("library/workflows/automation/activity/chat defaults are unchanged")
    func existingModeDefaultsAreByteIdentical() {
        #expect(
            ViewModeNormalization.normalizedViewMode(current: .chat(nil), forNewSidebarMode: .library)
                == .library(nil)
        )
        #expect(
            ViewModeNormalization.normalizedViewMode(current: .library(nil), forNewSidebarMode: .chat)
                == .chat(nil)
        )
        #expect(
            ViewModeNormalization.normalizedViewMode(current: .library(nil), forNewSidebarMode: .workflows)
                == .workflow(nil)
        )
        #expect(
            ViewModeNormalization.normalizedViewMode(current: .library(nil), forNewSidebarMode: .automation)
                == .automation
        )
        #expect(
            ViewModeNormalization.normalizedViewMode(current: .library(nil), forNewSidebarMode: .activity)
                == .activity(nil)
        )
    }

    @Test("the #1475 preservation rule still holds: an existing selection in the new mode's family is kept")
    func preservationRuleStillHolds() {
        let workflowItem = WorkflowSidebarItem(id: "w1", name: "W")
        #expect(
            ViewModeNormalization.normalizedViewMode(
                current: .workflow(workflowItem),
                forNewSidebarMode: .workflows
            ) == .workflow(workflowItem)
        )
        #expect(
            ViewModeNormalization.normalizedViewMode(
                current: .automation,
                forNewSidebarMode: .automation
            ) == .automation
        )
    }
}
