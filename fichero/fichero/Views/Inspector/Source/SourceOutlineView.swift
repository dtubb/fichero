import FicheroAPIClient
import SwiftUI

// MARK: - Source outline (#3440)

/// Document-scoped observable store for the generated source outline (#3440).
///
/// Wraps `GET /api/documents/{id}/outline` through the injected
/// `DocumentService` — no hand-rolled URL, no view-owned fetch. Holds
/// the flat, depth-ordered rows; the view folds them into a hierarchy.
///
/// Source **anchors** for reveal-in-Preview are engine work (#3441): today the
/// rows carry only id / depth / kind / label / count, so this is a native
/// hierarchy/drill-down mode, and rows do not pretend to be source anchors.
@MainActor
@Observable
final class DocumentOutlineStore {
    private(set) var rows: [Components.Schemas.DocumentOutlineRow] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var loadedDocumentId: String?

    func load(
        documentId: String,
        using service: DocumentService,
        force: Bool = false
    ) async {
        if !force, loadedDocumentId == documentId, loadError == nil { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            rows = try await service.documentOutline(documentId)
            loadedDocumentId = documentId
        } catch is CancellationError {
            // Superseded by a newer selection — keep current state.
        } catch {
            rows = []
            loadError = error.localizedDescription
            loadedDocumentId = nil
        }
    }
}

/// One node in the source-outline tree — the flat depth-list folded into a
/// hierarchy for the native `OutlineGroup` (#3440).
struct SourceOutlineNode: Identifiable, Hashable {
    let row: Components.Schemas.DocumentOutlineRow
    var children: [SourceOutlineNode]?

    var id: String { row.id }

    /// Fold a flat, depth-ordered row list into a tree. Rows arrive depth-first
    /// (a parent immediately followed by its deeper descendants), with `depth`
    /// giving the level, so a recursive descent reconstructs the hierarchy.
    /// `children` is `nil` (not `[]`) for leaves, so the native outline shows a
    /// disclosure triangle only where there is something to expand. Pure + testable.
    static func tree(
        from rows: [Components.Schemas.DocumentOutlineRow]
    ) -> [SourceOutlineNode] {
        guard let minDepth = rows.map(\.depth).min() else { return [] }
        var index = 0

        func parse(atDepth depth: Int) -> [SourceOutlineNode] {
            var nodes: [SourceOutlineNode] = []
            while index < rows.count, rows[index].depth == depth {
                let row = rows[index]
                index += 1
                let children: [SourceOutlineNode]?
                if index < rows.count, rows[index].depth > depth {
                    children = parse(atDepth: depth + 1)
                } else {
                    children = nil
                }
                nodes.append(SourceOutlineNode(row: row, children: children))
            }
            return nodes
        }

        return parse(atDepth: minDepth)
    }

    /// The source anchor for an outline row, or nil for a group/structural row
    /// that isn't a source anchor (#3440 + #3441). Page/structural rows the
    /// engine marks reveal-capable (`sourceCapability == "reveal"`) with a
    /// document id route through the shared source-navigation contract; group
    /// rows (no anchor) deliberately return nil rather than fake one. Pure +
    /// testable.
    static func navigationRequest(
        for row: Components.Schemas.DocumentOutlineRow
    ) -> ClaimSourceNavigationRequest? {
        guard row.sourceCapability == "reveal",
              let documentId = row.sourceDocumentId,
              !documentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return ClaimSourceNavigationRequest(documentId: documentId, pageLabel: row.pageLabel)
    }
}

/// Native document outline (#3440): the generated source hierarchy rendered as a
/// SwiftUI `List` with disclosure, so keyboard navigation, VoiceOver, and
/// full-row selection come from the platform. A deliberate hierarchy MODE inside
/// the Source section (see ``SourceSectionView``), not a permanent tab.
///
/// Source reveal for page/structural rows lands with #3441 (stable anchors);
/// until then this is drill-down/overview only.
struct SourceOutlineView: View {
    let documentId: String

    @Environment(DocumentService.self) private var documentService
    /// Per-window typed source-navigation bus (#3437) — reveal-capable outline
    /// rows route their source anchor through it, same contract as claims (#3440).
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?
    @State private var store = DocumentOutlineStore()
    @State private var selection: String?

    var body: some View {
        Group {
            if store.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let loadError = store.loadError {
                ContentUnavailableView {
                    Label("Couldn’t load outline", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(loadError)
                } actions: {
                    Button("Retry") {
                        Task { await store.load(documentId: documentId, using: documentService, force: true) }
                    }
                }
            } else if store.rows.isEmpty {
                ContentUnavailableView(
                    "No outline",
                    systemImage: "list.bullet.indent",
                    description: Text("This document has no structural outline yet.")
                )
            } else {
                List(
                    SourceOutlineNode.tree(from: store.rows),
                    children: \.children,
                    selection: $selection
                ) { node in
                    outlineRow(node.row)
                }
                .listStyle(.inset)
            }
        }
        .task(id: documentId) {
            await store.load(documentId: documentId, using: documentService)
        }
        // Selecting a reveal-capable page/structural row drives the reader to its
        // source via the shared contract (#3440/#3441); group rows no-op.
        .onChange(of: selection) { _, newSelection in
            guard let newSelection,
                  let row = store.rows.first(where: { $0.id == newSelection }),
                  let request = SourceOutlineNode.navigationRequest(for: row) else { return }
            claimSourceNavigationState?.request(request)
        }
    }

    private func outlineRow(_ row: Components.Schemas.DocumentOutlineRow) -> some View {
        HStack(spacing: 6) {
            Image(systemName: Self.icon(forKind: row.kind))
                .foregroundStyle(.secondary)
                .font(.caption)
            Text(row.label)
                .lineLimit(1)
            Spacer(minLength: 4)
            // `row.count` is a generated Int field (child/item count) on the
            // OpenAPI DocumentOutlineRow, not a collection — there is no
            // `isEmpty`, so the empty_count rule is a false positive here.
            // swiftlint:disable:next empty_count
            if row.count > 0 {
                Text("\(row.count)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .inspectorListRowTarget()
        .help(row.label)
    }

    /// SF Symbol for an outline row kind. Falls back to a generic marker so a new
    /// backend kind still renders (rather than a blank row).
    static func icon(forKind kind: String) -> String {
        switch kind.lowercased() {
        case "document", "file": return "doc.text"
        case "folder", "collection": return "folder"
        case "page": return "doc"
        case "section", "chunk": return "text.alignleft"
        case "entity", "person", "place", "organization": return "person.crop.circle"
        case "claim": return "quote.bubble"
        default: return "circle.fill"
        }
    }
}
