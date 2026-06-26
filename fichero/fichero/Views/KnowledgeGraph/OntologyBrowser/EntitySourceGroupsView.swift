import FicheroAPIClient
import SwiftUI

// MARK: - Entity Source Groups View

/// Claims for one entity grouped by source document + page label,
/// rendered as dense semicolon-separated prose. Each group becomes a
/// titled section; each clause is a discrete text run that can later
/// be made tappable for PDF jump-to. Backed by the entity inspector
/// endpoint (#1183).
struct EntitySourceGroupsView: View {
    let entityId: String

    @State private var inspectorData: Components.Schemas.EntityInspectorResponse?
    @State private var isLoading = false
    @State private var loadError: String?

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading source groups…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if let data = inspectorData {
                sourceGroupsContent(data)
            } else {
                Color.clear
            }
        }
        .task(id: entityId) {
            await loadInspector()
        }
    }

    // MARK: - Content

    @ViewBuilder
    private func sourceGroupsContent(_ data: Components.Schemas.EntityInspectorResponse) -> some View {
        let groups = groupedClaims(data)
        let docNames = documentNameMap(data)

        if groups.isEmpty {
            VStack(spacing: 8) {
                Image(systemName: "doc.text")
                    .font(.system(size: 28))
                    .foregroundStyle(.secondary)
                Text("No source groups")
                    .font(.subheadline)
                Text("Claims with source document metadata will appear here")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding()
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ForEach(groups, id: \.key) { group in
                        sourceGroupSection(
                            key: group.key,
                            claims: group.claims,
                            docNames: docNames
                        )
                    }
                }
                .padding()
            }
        }
    }

    @ViewBuilder
    private func sourceGroupSection(
        key: SourceGroupKey,
        claims: [Components.Schemas.KnowledgeClaim],
        docNames: [String: String]
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Section header: document name + page label
            let docName = docNames[key.docId] ?? (key.docId.isEmpty ? "Unknown source" : String(key.docId.prefix(8)))
            let header = key.page.isEmpty ? docName : "\(docName) — p. \(key.page)"

            HStack(spacing: 4) {
                Image(systemName: "doc.text.fill")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(header)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(claims.count) claim\(claims.count == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            // Dense semicolon-separated prose
            denseClauseText(claims)
        }
        .padding(10)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func denseClauseText(_ claims: [Components.Schemas.KnowledgeClaim]) -> some View {
        if let combined = buildClauseAttributedString(claims) {
            Text(combined)
                .font(.callout)
                .textSelection(.enabled)
        } else {
            Text("(no claim text)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func buildClauseAttributedString(
        _ claims: [Components.Schemas.KnowledgeClaim]
    ) -> AttributedString? {
        let parts: [AttributedString] = claims.compactMap { claim in
            let text = claim.text
            guard !text.isEmpty else { return nil }
            var str = AttributedString(text.trimmingCharacters(in: .init(charactersIn: ".")))
            var annotations: [String] = []
            if let time = claim.temporalContext { annotations.append(time) }
            if let place = claim.claimLocation { annotations.append(place) }
            if let speaker = claim.speakerName { annotations.append("— \(speaker)") }
            if !annotations.isEmpty {
                var ann = AttributedString(" (\(annotations.joined(separator: " · ")))")
                ann.foregroundColor = .secondary
                ann.font = .caption
                str += ann
            }
            return str
        }
        guard !parts.isEmpty else { return nil }
        var combined = AttributedString()
        for (idx, part) in parts.enumerated() {
            combined += part
            if idx < parts.count - 1 {
                var sep = AttributedString("; ")
                sep.foregroundColor = .secondary
                combined += sep
            }
        }
        return combined
    }

    // MARK: - Data Helpers

    private struct SourceGroupKey: Hashable, CustomStringConvertible {
        let docId: String
        let page: String
        var description: String { "\(docId)|\(page)" }
    }

    private struct SourceGroup {
        let key: SourceGroupKey
        var claims: [Components.Schemas.KnowledgeClaim]
    }

    private func groupedClaims(
        _ data: Components.Schemas.EntityInspectorResponse
    ) -> [SourceGroup] {
        var order: [SourceGroupKey] = []
        var map: [SourceGroupKey: [Components.Schemas.KnowledgeClaim]] = [:]

        for claim in data.claims {
            let key = SourceGroupKey(
                docId: claim.sourceDocumentId ?? "",
                page: claim.sourcePageLabel ?? ""
            )
            if map[key] == nil {
                order.append(key)
            }
            map[key, default: []].append(claim)
        }
        return order.map { SourceGroup(key: $0, claims: map[$0] ?? []) }
    }

    private func documentNameMap(
        _ data: Components.Schemas.EntityInspectorResponse
    ) -> [String: String] {
        var names: [String: String] = [:]
        for doc in data.documents {
            if let docId = doc.id {
                names[docId] = doc.name
            }
        }
        return names
    }

    // MARK: - Load

    private func loadInspector() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        loadError = nil
        do {
            inspectorData = try await library.entityService.getEntityInspector(entityId)
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }
}
