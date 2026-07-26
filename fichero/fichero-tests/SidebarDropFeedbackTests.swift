@testable import Fichero
import Foundation
import Testing

/// Locks the multi-item drop feedback contract (#7 from the drag audit):
/// partially-applied drops summarise what was skipped and why; clean drops
/// stay silent; the Inbox empty-id sentinel never counts as a skipped item.
struct SidebarDropFeedbackTests {

    @Test("clean drop produces no banner")
    func cleanDropIsSilent() {
        #expect(sidebarDropSkipMessage(moved: 3, skips: SidebarDropSkipSummary()) == nil)
        #expect(sidebarDropSkipMessage(moved: 0, skips: SidebarDropSkipSummary()) == nil)
    }

    @Test("partial drop reports moved-of-total with reasons")
    func partialDropSummarises() {
        var skips = SidebarDropSkipSummary()
        skips.crossSection = 2
        skips.circular = 1
        let message = sidebarDropSkipMessage(moved: 2, skips: skips)
        #expect(message == "Moved 2 of 5 items (skipped: 2 in a different section, 1 would nest a folder inside itself).")
    }

    @Test("fully-rejected drop says nothing was moved")
    func fullyRejectedDropSummarises() {
        var skips = SidebarDropSkipSummary()
        skips.selfDrop = 1
        let message = sidebarDropSkipMessage(moved: 0, skips: skips)
        #expect(message == "Nothing was moved (1 item skipped: 1 dropped onto itself).")
    }

    // MARK: - Option-drag copy (⌥ at drop time)

    @Test("Option copies documents; everything else stays a move")
    func optionDragCopyIsDocumentOnly() {
        #expect(sidebarDropOperation(optionHeld: true, kind: .document) == .copy)
        // No Option → move, always.
        #expect(sidebarDropOperation(optionHeld: false, kind: .document) == .move)
        // Kinds without a targeted duplicate endpoint keep move semantics.
        #expect(sidebarDropOperation(optionHeld: true, kind: .savedSearch) == .move)
        #expect(sidebarDropOperation(optionHeld: true, kind: .workflow) == .move)
        #expect(sidebarDropOperation(optionHeld: true, kind: .unknown) == .move)
    }

    @Test("copy path routes through the audited document.duplicate action")
    func copyPathUsesAuditedAction() throws {
        let handlers = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift")
        // ⌥ sampled once at the drop moment, then per-item operation dispatch.
        #expect(handlers.contains("let optionHeldAtDrop = sidebarOptionKeyIsHeld()"))
        #expect(handlers.contains(#"name: "document.duplicate""#))
        // The engine owns cycle/lock rules; failures surface on the banner.
        #expect(handlers.contains("sidebarState.dropErrorMessage = error.localizedDescription"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
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
        let message = sidebarDropSkipMessage(moved: 0, skips: skips)
        #expect(
            message ==
                "Nothing was moved (3 items skipped: 1 in a different section, "
                + "1 dropped onto itself, 1 would nest a folder inside itself)."
        )
    }
}
