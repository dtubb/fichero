import SwiftUI

/// One row of a document's hierarchical outline, as returned by
/// GET /api/documents/{id}/outline (#1491). The endpoint returns a flat,
/// depth-first preorder list; `depth` drives the tree nesting.
struct DocumentOutlineRow: Codable, Identifiable, Hashable {
    let id: String
    let depth: Int
    let kind: String
    let label: String
    let count: Int
}

/// Envelope for the outline endpoint.
struct DocumentOutlineResponse: Codable {
    let documentId: String
    let rows: [DocumentOutlineRow]
    let count: Int

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case rows
        case count
    }
}

/// Nested node built from the flat outline rows so SwiftUI's `List(_:children:)`
/// can render a collapsible disclosure tree. Leaves carry `children == nil`.
private struct OutlineNode: Identifiable, Hashable {
    let row: DocumentOutlineRow
    var children: [OutlineNode]?
    var id: String { row.id }
}

/// Unified drill-down inspector tab (Thing 1 of the thinking-layer, #1492):
/// a collapsible source outline — chapters/sections → pages →
/// annotations/entities/claims — over the merged outline endpoint (#1491).
/// Added as a tab ALONGSIDE the existing inspector tabs; it removes none.
struct SourceOutlineView: View {
    let documentId: String

    @EnvironmentObject private var apiClient: APIClient
    @State private var nodes: [OutlineNode] = []
    @State private var isLoading = false
    @State private var loadError: String?

    var body: some View {
        Group {
            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let loadError {
                emptyState(
                    title: "Couldn't load outline",
                    message: loadError,
                    icon: "exclamationmark.triangle"
                )
            } else if nodes.isEmpty {
                emptyState(
                    title: "No outline yet",
                    message: "This document has no structured outline. Run extraction to build chapters, sections, and pages.",
                    icon: "list.bullet.indent"
                )
            } else {
                List(nodes, children: \.children) { node in
                    outlineRow(node.row)
                }
                .listStyle(.sidebar)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: documentId) { await load() }
    }

    private func outlineRow(_ row: DocumentOutlineRow) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon(for: row.kind))
                .foregroundStyle(.secondary)
                .frame(width: 16)
            Text(row.label)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer(minLength: 4)
            // `row.count` is a numeric child-count badge, not a collection — empty_count is a false positive here.
            if row.count > 0 {  // swiftlint:disable:this empty_count
                Text("\(row.count)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color.secondary.opacity(0.12)))
            }
        }
        .help("\(row.kind.capitalized): \(row.label)")
    }

    private func icon(for kind: String) -> String {
        switch kind.lowercased() {
        case "chapter": return "book.closed"
        case "section": return "list.bullet.indent"
        case "page": return "doc"
        case "annotation": return "highlighter"
        case "entity", "person", "place", "organization": return "person.crop.circle"
        case "claim": return "quote.bubble"
        default: return "circle.fill"
        }
    }

    @ViewBuilder
    private func emptyState(title: String, message: String, icon: String) -> some View {
        VStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 32))
                .foregroundStyle(.tertiary)
            Text(title)
                .font(.headline)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 260)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let response: DocumentOutlineResponse = try await apiClient.get(
                "/documents/\(documentId)/outline"
            )
            nodes = Self.buildTree(response.rows)
        } catch {
            loadError = error.localizedDescription
        }
    }

    /// Build a nested tree from the flat depth-first preorder rows: each run of
    /// rows at `depth + 1` immediately following a row is that row's children.
    private static func buildTree(_ rows: [DocumentOutlineRow]) -> [OutlineNode] {
        var index = 0
        func consume(atDepth depth: Int) -> [OutlineNode] {
            var result: [OutlineNode] = []
            while index < rows.count, rows[index].depth == depth {
                let row = rows[index]
                index += 1
                let children = consume(atDepth: depth + 1)
                result.append(OutlineNode(row: row, children: children.isEmpty ? nil : children))
            }
            return result
        }
        return consume(atDepth: rows.first?.depth ?? 0)
    }
}
