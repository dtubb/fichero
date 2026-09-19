@testable import Fichero
import Testing

/// spec: panes-workspaces `panes.model.per-pane-scope-and-kind-unread` (#4887) /
/// kg-tables `kg.tables.pane-kind-mismatch` (#4884, BROKEN → this delivery).
///
/// `LibraryView.effectiveKind` is the pure decision the pane-head content-kind
/// chip and the window's sidebar collection both feed into. Tested directly,
/// off-view — no `LibraryView` needs mounting for any of these.
struct LibraryEffectiveContentKindTests {

    @Test("no explicit kind anywhere — the window's sidebar collection decides (pre-#4884 behavior)")
    func windowDecidesWhenNothingIsExplicit() {
        #expect(
            LibraryView.effectiveKind(
                paneKind: nil, localOverride: nil,
                contentCollection: .entities, searchAutoSurfaceKind: nil
            ) == .entities
        )
        #expect(
            LibraryView.effectiveKind(
                paneKind: nil, localOverride: nil,
                contentCollection: .claims, searchAutoSurfaceKind: nil
            ) == .claims
        )
        #expect(
            LibraryView.effectiveKind(
                paneKind: nil, localOverride: nil,
                contentCollection: .documents, searchAutoSurfaceKind: nil
            ) == .documents
        )
    }

    @Test("a search auto-surface still wins under .documents when nothing is explicit")
    func searchAutoSurfaceWinsUnderDocumentsCollection() {
        #expect(
            LibraryView.effectiveKind(
                paneKind: nil, localOverride: nil,
                contentCollection: .documents, searchAutoSurfaceKind: .claims
            ) == .claims
        )
    }

    @Test("an explicit per-pane kind (the chip) wins over the window's sidebar collection outright — including Documents")
    func explicitPaneKindWinsOverWindow() {
        // The exact #4884 bug: kind chip says Documents but the sidebar drives
        // Entities. An explicit pane must stay what it was explicitly set to —
        // the maintainer's "Library panes are not linked" ruling — even for
        // "Documents", which used to be treated as "no opinion".
        #expect(
            LibraryView.effectiveKind(
                paneKind: .documents, localOverride: nil,
                contentCollection: .entities, searchAutoSurfaceKind: nil
            ) == .documents
        )
        #expect(
            LibraryView.effectiveKind(
                paneKind: .claims, localOverride: nil,
                contentCollection: .entities, searchAutoSurfaceKind: nil
            ) == .claims
        )
        #expect(
            LibraryView.effectiveKind(
                paneKind: .entities, localOverride: nil,
                contentCollection: .claims, searchAutoSurfaceKind: nil
            ) == .entities
        )
    }

    @Test("the local fallback (no pane slot — the compact iPhone reader stack) is exactly as explicit and sticky")
    func localOverrideWinsWhenThereIsNoSlot() {
        #expect(
            LibraryView.effectiveKind(
                paneKind: nil, localOverride: .entities,
                contentCollection: .documents, searchAutoSurfaceKind: nil
            ) == .entities
        )
        #expect(
            LibraryView.effectiveKind(
                paneKind: nil, localOverride: .documents,
                contentCollection: .claims, searchAutoSurfaceKind: nil
            ) == .documents
        )
    }

    @Test("a slotted pane's own config wins over the local fallback when (hypothetically) both are set")
    func paneKindTakesPrecedenceOverLocalOverride() {
        #expect(
            LibraryView.effectiveKind(
                paneKind: .claims, localOverride: .entities,
                contentCollection: .documents, searchAutoSurfaceKind: nil
            ) == .claims
        )
    }
}
