import FicheroAPIClient
import Foundation
import Observation
import OSLog

//  Extracted for file_length (#5113). Byte-for-byte, behaviour unchanged. Imports are the
//  SOURCE file's; the path was asserted free; the cut is above the declaration's attributes
//  and doc comment, not at its keyword.

//  The logger moved with the model it is named for (category "LibraryOutlineModel"). A
//  `private let` is FILE-scoped, so leaving it behind made it inaccessible from here — and
//  its only remaining mention over there was its own declaration.
private let logger = Logger(subsystem: "app.fichero.fichero", category: "LibraryOutlineModel")

/// Lazily fetches and caches per-document rollup counts so the outline
/// Table can show child-group rows under an expanded document without
/// pre-fetching every document's children (#2258).
///
/// Build the child-group nodes for a document from its cached rollup;
/// a document with no cached rollup yet returns `nil` children (the
/// disclosure stays empty until `loadRollup` resolves), keeping the
/// collapsed-by-default Table cheap.
@MainActor
@Observable
final class LibraryOutlineModel {
    /// document id -> rollup counts. Bumping this dictionary re-renders
    /// only the affected rows (value identity is per-document).
    /// Internal (not private) so tests can inject state directly.
    var rollups: [String: Components.Schemas.DocumentRollupResponse] = [:]
    /// In-flight / failed ids so we never double-fetch or hammer a
    /// 404'd document on every disclosure toggle.
    private var requested: Set<String> = []

    /// Page documents grouped by their parent document id.
    /// Populated by LibraryView from documentStore.currentDocuments
    /// (pages are already loaded — no extra fetch needed).
    var pagesByParentId: [String: [Document]] = [:]

    /// Own-scope artifacts (non-descendant) by document id.
    /// Populated on demand when a document row is expanded.
    /// Internal (not private) so tests can inject state directly.
    var artifactsByDocumentId: [String: [Artifact]] = [:]
    private var artifactRequested: Set<String> = []
    /// A folder's child documents (#5282), from `DocumentStore.cacheSidebarChildren`: the cache the
    /// sidebar already fills, so expanding in either place fetches once.
    var childDocumentsByParentId: [String: [Document]] = [:]

    private let service: EntityService
    private let artifactService: ArtifactService

    init(service: EntityService, artifactService: ArtifactService) {
        self.service = service
        self.artifactService = artifactService
    }

    /// Fetch the rollup for a document once. Idempotent: repeat calls
    /// for the same id (already loaded or in flight) are no-ops.
    func loadRollup(for documentId: String) async {
        guard rollups[documentId] == nil, !requested.contains(documentId) else { return }
        requested.insert(documentId)
        do {
            rollups[documentId] = try await service.documentRollup(documentId: documentId)
        } catch {
            // A missing/failed rollup must not break the table — the row
            // simply shows no disclosed children. `requested` keeps the
            // failure sticky so we don't retry on every toggle.
        }
    }

    /// Fetch own-scope artifacts for a document once (non-descendant, matching
    /// the V2 inspector scope). Idempotent — subsequent calls while in-flight
    /// or already loaded are no-ops.
    func loadArtifacts(for documentId: String) async {
        guard artifactsByDocumentId[documentId] == nil,
              !artifactRequested.contains(documentId) else { return }
        artifactRequested.insert(documentId)
        do {
            let arts = try await artifactService.getArtifacts(
                forDocumentId: documentId,
                includeDescendants: false
            )
            artifactsByDocumentId[documentId] = arts
        } catch {
            logger.debug("Artifact load failed for \(documentId): \(error)")
            // Failure keeps the count-fallback group visible until next expansion.
        }
    }

    /// Build the child rows for one document.
    /// - Child documents (a folder's contents) → document rows, first, as Finder lists them (#5282).
    /// - Pages → individual page item rows (pagesByParentId, else the fetched children).
    /// - Artifacts → individual artifact item rows once loaded; count-group fallback until then.
    /// - Notes → a count-group row.
    /// Entities and claims are not library rows (#5282, maintainer ruling 2026-09-29); they live in
    /// the inspector and the knowledge views.
    /// Returns `nil` while nothing is known yet (the disclosure shows but is empty).
    func childNodes(for document: Document) -> [LibraryOutlineNode]? {
        let fetched = childDocumentsByParentId[document.id]
        let rollup = rollups[document.id]
        if fetched == nil && rollup == nil { return nil }
        var nodes = (fetched ?? []).filter { $0.docType != .page }
            .map { LibraryOutlineNode.document($0, children: nil) }
        let pages = pagesByParentId[document.id] ?? (fetched ?? []).filter { $0.docType == .page }
        nodes += pages.sorted { ($0.sequence ?? 0) < ($1.sequence ?? 0) }
            .map { LibraryOutlineNode.pageItem($0, parent: document) }
        if let rollup {
            nodes += artifactChildNodes(for: document, rollup: rollup, type: .artifacts)
            nodes += noteChildNodes(for: document, rollup: rollup, type: .notes)
        }
        return nodes
    }

    private func artifactChildNodes(
        for document: Document,
        rollup: Components.Schemas.DocumentRollupResponse,
        type: LibraryOutlineNode.ChildType
    ) -> [LibraryOutlineNode] {
        if let arts = artifactsByDocumentId[document.id] {
            return arts.map { LibraryOutlineNode.artifactItem($0, parent: document) }
        } else if rollup.artifacts > 0 {
            // Show count summary until per-document fetch completes.
            return [LibraryOutlineNode.childGroup(type, document: document, count: rollup.artifacts)]
        }
        return []
    }

    private func noteChildNodes(
        for document: Document,
        rollup: Components.Schemas.DocumentRollupResponse,
        type: LibraryOutlineNode.ChildType
    ) -> [LibraryOutlineNode] {
        let count = type.count(in: rollup)
        return count > 0 ? [LibraryOutlineNode.childGroup(type, document: document, count: count)] : []
    }

    /// Assemble the top-level outline nodes for the visible documents.
    /// Each document node carries whatever child nodes are already known;
    /// expanding a row triggers `loadRollup` + `loadArtifacts` to fill them in.
    func nodes(for documents: [Document]) -> [LibraryOutlineNode] {
        documents.map { document in
            LibraryOutlineNode.document(document, children: childNodes(for: document))
        }
    }
}
