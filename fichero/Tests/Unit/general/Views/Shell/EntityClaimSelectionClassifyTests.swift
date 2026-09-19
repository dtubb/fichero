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
              // #4862 split the old combined "case .pages, .artifacts, .notes, nil:"
              // into three cases — "case .pages:" is now the next one after .claims.
              let nextCaseRange = body.range(of: "case .pages:", range: claimCaseRange.upperBound..<body.endIndex)
        else {
            Issue.record("could not locate the .claims branch")
            return
        }
        let claimBranch = body[claimCaseRange.upperBound..<nextCaseRange.lowerBound]
        #expect(claimBranch.contains("return"))
        #expect(!claimBranch.contains("documentService.getDocument"))
        #expect(!claimBranch.contains("detailDocument ="), "a claim selection must not touch detailDocument — its own onOpenSource path does not")
    }

    // MARK: - #4862: page/artifact/note rows no longer leak a composite id

    /// A page row promotes ITS OWN page — `parsed.itemId`, the page's own
    /// bare document id, never the composite `"<doc>:page:<id>"` string.
    @Test("a page row promotes its own page via the bare item id, never the composite id")
    func pageRowPromotesItsOwnPageViaBareId() throws {
        let body = try functionBody()
        guard let pagesCaseRange = body.range(of: "case .pages:"),
              let nextCaseRange = body.range(of: "case .artifacts, .notes:", range: pagesCaseRange.upperBound..<body.endIndex)
        else {
            Issue.record("could not locate the .pages branch")
            return
        }
        let pagesBranch = body[pagesCaseRange.upperBound..<nextCaseRange.lowerBound]
        #expect(pagesBranch.contains("documentStore.documentService.getDocument(itemId)"))
        #expect(pagesBranch.contains("detailDocument = page"))
        // No composite id may reach the service call — only `itemId`.
        #expect(!pagesBranch.contains("getDocument(primaryId)"))
        #expect(!pagesBranch.contains("getDocument(firstId)"))
    }

    /// Artifact and note rows are a safe no-op here — the Table view's own
    /// `.onChange(of: selection)` already resolves them correctly via its
    /// live outline tree; this ContentView-level branch must not guess at a
    /// parent lookup, and above all must not let the composite id reach the
    /// generic document-promotion path below.
    @Test("artifact and note rows are a safe no-op, never reaching document promotion")
    func artifactAndNoteRowsAreASafeNoOp() throws {
        let body = try functionBody()
        guard let caseRange = body.range(of: "case .artifacts, .notes:"),
              let nextCaseRange = body.range(of: "case nil:", range: caseRange.upperBound..<body.endIndex)
        else {
            Issue.record("could not locate the .artifacts, .notes branch")
            return
        }
        let branch = body[caseRange.upperBound..<nextCaseRange.lowerBound]
        #expect(branch.contains("return"))
        #expect(!branch.contains("documentService.getDocument"))
        #expect(!branch.contains("detailDocument ="))
    }
}
