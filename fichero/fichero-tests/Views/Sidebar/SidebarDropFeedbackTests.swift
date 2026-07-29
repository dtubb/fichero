@testable import Fichero
import Foundation
import Testing

/// Locks the multi-item drop feedback contract (#7 from the drag audit):
/// partially-applied drops summarise what was skipped and why; clean drops
/// stay silent; the Inbox empty-id sentinel never counts as a skipped item.
struct SidebarDropFeedbackTests {

    @Test("clean drop produces no banner")
    func cleanDropIsSilent() {
        #expect(sidebarDropOutcomeMessage(applied: 3, failed: 0, skips: SidebarDropSkipSummary()) == nil)
        #expect(sidebarDropOutcomeMessage(applied: 0, failed: 0, skips: SidebarDropSkipSummary()) == nil)
    }

    @Test("partial drop reports applied-of-total with reasons")
    func partialDropSummarises() {
        var skips = SidebarDropSkipSummary()
        skips.crossSection = 2
        skips.circular = 1
        let message = sidebarDropOutcomeMessage(applied: 2, failed: 0, skips: skips)
        #expect(message == "Dropped 2 of 5 items (2 in a different section, 1 would nest a folder inside itself).")
    }

    @Test("async copy/alias failures count as real outcomes, not successes")
    func asyncFailuresAreCounted() {
        // Review finding: the old banner counted dispatched Tasks as applied.
        let message = sidebarDropOutcomeMessage(applied: 1, failed: 2, skips: SidebarDropSkipSummary())
        #expect(message == "Dropped 1 of 3 items (2 failed).")
        let allFailed = sidebarDropOutcomeMessage(applied: 0, failed: 3, skips: SidebarDropSkipSummary())
        #expect(allFailed == "Nothing was dropped (3 items: 3 failed).")
    }

    @Test("fully-rejected drop says nothing was dropped")
    func fullyRejectedDropSummarises() {
        var skips = SidebarDropSkipSummary()
        skips.selfDrop = 1
        let message = sidebarDropOutcomeMessage(applied: 0, failed: 0, skips: skips)
        #expect(message == "Nothing was dropped (1 item: 1 dropped onto itself).")
    }

    // MARK: - Option-drag copy (⌥ at drop time)

    @Test("Finder modifier grammar: plain=move, ⌥=copy, ⌘⌥=alias — documents only")
    func modifierDragGrammarIsDocumentOnly() {
        #expect(sidebarDropOperation(optionHeld: false, commandHeld: false, kind: .document) == .move)
        #expect(sidebarDropOperation(optionHeld: true, commandHeld: false, kind: .document) == .copy)
        #expect(sidebarDropOperation(optionHeld: true, commandHeld: true, kind: .document) == .alias)
        // ⌘ alone is the multi-select modifier, never a drop operation.
        #expect(sidebarDropOperation(optionHeld: false, commandHeld: true, kind: .document) == .move)
        // Kinds without targeted duplicate/alias endpoints keep move semantics.
        #expect(sidebarDropOperation(optionHeld: true, commandHeld: false, kind: .savedSearch) == .move)
        #expect(sidebarDropOperation(optionHeld: true, commandHeld: true, kind: .workflow) == .move)
        #expect(sidebarDropOperation(optionHeld: true, commandHeld: false, kind: .unknown) == .move)
    }

    @Test("alias naming follows the Finder same-folder rule")
    func aliasNamingRule() {
        #expect(sidebarAliasName(sourceName: "Paper", sourceParentId: "f1", targetParentId: "f1") == "Paper alias")
        #expect(sidebarAliasName(sourceName: "Paper", sourceParentId: "f1", targetParentId: "f2") == "Paper")
        #expect(sidebarAliasName(sourceName: "Loose", sourceParentId: nil, targetParentId: nil) == "Loose alias")
    }

    @Test("insertion drops route ⌥/⌘⌥ through the positioned executor")
    func insertionDropsSupportModifierGrammar() throws {
        for path in [
            "Views/Sidebar/Sections/SidebarView+UnifiedRows.swift",
            "Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift"
        ] {
            let source = try appSource(path)
            #expect(source.contains("sidebarApplyInsertionDropOperation("), Comment(rawValue: path))
            #expect(
                source.contains("sidebarDropOperation(modifiers: .current(), kind: .document)"),
                Comment(rawValue: path)
            )
        }
    }

    @Test("copy path routes through the audited document.duplicate action")
    func copyPathUsesAuditedAction() throws {
        let handlers = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift")
        // Modifiers sampled once at the drop moment, then per-item dispatch;
        // copy/alias outcomes are AWAITED before the banner claims anything.
        #expect(handlers.contains("let modifiersAtDrop = SidebarDropModifiers.current()"))
        #expect(handlers.contains("finishFolderDrop("))
        // The audited copy itself moved into the shared drop-operation
        // executor (SidebarDropOperation) — assert it there, not in the
        // per-row handlers file.
        let executor = try appSource("Views/Sidebar/ItemRow/SidebarDropOperation.swift")
        #expect(executor.contains(#"name: "document.duplicate""#))
        // The engine owns cycle/lock rules; failures surface on the banner.
        #expect(handlers.contains("sidebarState.dropErrorMessage = error.localizedDescription"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("skip counts sum across reasons")
    func skipTotals() {
        var skips = SidebarDropSkipSummary()
        skips.crossSection = 1
        skips.selfDrop = 1
        skips.circular = 1
        #expect(skips.total == 3)
        let message = sidebarDropOutcomeMessage(applied: 0, failed: 0, skips: skips)
        #expect(
            message ==
                "Nothing was dropped (3 items: 1 in a different section, "
                + "1 dropped onto itself, 1 would nest a folder inside itself)."
        )
    }
}
