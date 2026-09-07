import FicheroAPIClient
import SwiftUI

// MARK: - Entity Source Groups View

/// Claims for one entity grouped by source document + page label,
/// rendered as dense semicolon-separated prose. Each group becomes a
/// titled section; each clause is a discrete text run that can later
/// be made tappable for PDF jump-to. Backed by the entity inspector
/// endpoint (#1183).
struct EntitySourceGroupsView: View {
    /// THIS surface's entity service — the library the browser is IN.
    ///
    /// It resolved `LibraryManager.shared.globalLibrary`, which is not
    /// "the current library" but the one holding the RESERVED id. The
    /// services were already injected per window (`libraryServiceEnvironment`);
    /// this surface simply never read them. Optional so a host that
    /// injects none fails VISIBLY rather than operating on another
    /// library's graph (#4306/#4461).
    @Environment(EntityService.self) private var entityService: EntityService?

    /// The SHARED source cursor (#4393 part 2) — the same seam the digest
    /// biography, the annotations list, the source outline and the KG web pane
    /// write to. This grouped-prose view was the last claim surface whose clauses
    /// could not get back to the page; making each clause a producer here — rather
    /// than a second addressing scheme — is what "a statement must lead to its
    /// source" (Daniel, 2026-09-04) asks for. Optional → a safe no-op without a
    /// host that injects it.
    @Environment(ClaimSourceNavigationState.self)
    private var claimSourceNavigationState: ClaimSourceNavigationState?

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
        if let combined = Self.buildClauseAttributedString(claims) {
            // Each clause IS a claim, and a claim knows its page — so each clause
            // is a door to the source (Daniel, 2026-09-04). The clause keeps
            // `textSelection` for copy-then-search; the in-prose link opens the
            // page with the passage lit through the shared cursor. Mirrors
            // EntityDigestView.biographyAttributed exactly — one link scheme, one
            // producer, the reader/preview latch consumes it.
            Text(combined)
                .font(.callout)
                .textSelection(.enabled)
                .environment(\.openURL, OpenURLAction { url in
                    guard url.scheme == Self.claimLinkScheme,
                          let claimId = url.host ?? url.pathComponents.dropFirst().first,
                          let claim = claims.first(where: { $0.id == claimId }),
                          let request = ClaimSourceRequest.request(for: claim)
                    else { return .discarded }
                    claimSourceNavigationState?.request(request)
                    return .handled
                })
        } else {
            Text("(no claim text)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    /// Custom scheme for the in-prose clause links; never leaves the view.
    static let claimLinkScheme = "fichero-claim"

    /// Build the dense semicolon-separated prose for a source group, each clause
    /// carrying a link to its claim's source page. A clause with no honest
    /// destination (no id, or no recorded document) stays plain text — a link
    /// that goes nowhere is worse than no link (the #4393 precision rule). Static
    /// so the clause/link mapping is testable without mounting the view.
    static func buildClauseAttributedString(
        _ claims: [Components.Schemas.KnowledgeClaim]
    ) -> AttributedString? {
        let parts: [AttributedString] = claims.compactMap { claim in
            let text = claim.text
            guard !text.isEmpty else { return nil }
            var str = AttributedString(text.trimmingCharacters(in: .init(charactersIn: ".")))
            // Only link a clause that can actually reach its source — otherwise
            // it reads as tappable and dead-ends.
            if let id = claim.id, ClaimSourceRequest.request(for: claim) != nil {
                // URLComponents, not a string-built URL: this is an INTERNAL link
                // scheme for tappable prose, and the raw-networking guards ban
                // string URL construction outright rather than guessing intent.
                var linkParts = URLComponents()
                linkParts.scheme = claimLinkScheme
                linkParts.host = id
                if let url = linkParts.url {
                    str.link = url
                    // Prose, not a wall of hyperlink-blue: keep body color and
                    // mark tappability with a subtle underline (mirrors the digest).
                    str.foregroundColor = .primary
                    str.underlineStyle = .single
                }
            }
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
        guard let entityService else {
            loadError = "This window has no library to read the entity from."
            return
        }
        isLoading = true
        loadError = nil
        do {
            inspectorData = try await entityService.getEntityInspector(entityId)
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }
}
