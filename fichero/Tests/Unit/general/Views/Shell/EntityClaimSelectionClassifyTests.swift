@testable import Fichero
import Foundation
import Testing

/// #4850 — `ContentView.handleBrowserSelectionChange` classifies the
/// selected row's OWN id first, via `LibraryOutlineNode.parse(nodeId:)`,
/// instead of relying on the ambient "which collection is the sidebar
/// showing" flag. The prior code passed the row's COMPOSITE outline id
/// ("<doc>:entity:<id>") straight to `kgFocusState.focusEntity(entityId:)`,
/// which then asked the engine for `GET /api/entities/<doc>:entity:<id>` —
/// a guaranteed 404, surfaced as "Entity Unavailable" in the inspector.
///
/// Source-scan: `handleBrowserSelectionChange` is an instance method on
/// `ContentView` with heavy dependencies (`kgFocusState`, `documentStore`,
/// `browserSelection`, …) with no seam to construct and exercise in a unit
/// test — the same limitation this codebase's other `ContentView`-glue
/// tests accept (see `WorkflowRunSurfaceSelectionTests`'s own structural
/// pins).
///
/// Spec: kg-entity-inspector `kg.entity.select.inspector-shows-entity`.
struct EntityClaimSelectionClassifyTests {

    private func source() throws -> String {
        try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView+StateEvents.swift"),
            encoding: .utf8
        )
    }

    /// Slice `handleBrowserSelectionChange`'s own body so these assertions
    /// cannot be satisfied by an unrelated function elsewhere in the file.
    private func functionBody() throws -> String {
        let text = try source()
        let start = try #require(
            text.range(of: "func handleBrowserSelectionChange(_ newSelection: Set<String>) {"),
            "handleBrowserSelectionChange is gone — this guard no longer measures anything"
        )
        let end = try #require(
            text.range(of: "\n    /// Handles `.onReceive", range: start.upperBound..<text.endIndex),
            "could not find the end of handleBrowserSelectionChange — the next function moved"
        )
        return String(text[start.upperBound..<end.lowerBound])
    }

    @Test("the row is classified from its OWN id before the ambient collection flag")
    func classifiesBeforeAmbientFlag() throws {
        let body = try functionBody()
        let classifyRange = try #require(body.range(of: "LibraryOutlineNode.parse(nodeId: primaryId)"))
        let ambientFlagRange = try #require(body.range(of: "if isEntityLibrarySelection {"))
        #expect(
            classifyRange.lowerBound < ambientFlagRange.lowerBound,
            "the row's own id must be classified BEFORE falling back to the ambient collection flag"
        )
    }

    @Test("an entity row focuses the BARE item id, never the composite outline id (#4850)")
    func entityRowFocusesBareId() throws {
        let body = try functionBody()
        #expect(body.contains("case .entities:"))
        #expect(body.contains("kgFocusState.focusEntity(entityId: itemId)"))
        // The composite must never reach focusEntity directly inside the
        // new classify-first block — only `parsed.itemId`, the bare id.
        #expect(!body.contains("kgFocusState.focusEntity(entityId: primaryId)"))
        #expect(!body.contains("kgFocusState.focusEntity(entityId: firstId)\n                // #4850"))
    }

    @Test("a claim row never reaches the document-promotion path (#4850)")
    func claimRowNeverReachesDocumentPromotion() throws {
        let body = try functionBody()
        guard let claimCaseRange = body.range(of: "case .claims:"),
              let nextCaseRange = body.range(of: "case .pages, .artifacts, .notes, nil:", range: claimCaseRange.upperBound..<body.endIndex)
        else {
            Issue.record("could not locate the .claims branch")
            return
        }
        let claimBranch = body[claimCaseRange.upperBound..<nextCaseRange.lowerBound]
        #expect(claimBranch.contains("return"))
        #expect(!claimBranch.contains("documentService.getDocument"))
        #expect(!claimBranch.contains("detailDocument ="), "a claim selection must not touch detailDocument — its own onOpenSource path does not")
    }
}
