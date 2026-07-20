import FicheroAPIClient
import Foundation
import SwiftUI

// MARK: - Raw metadata JSON editing

extension EntityDetailView {
    func saveMetadataJSON() async {
        isSavingMetadata = true
        defer { isSavingMetadata = false }
        guard LibraryManager.shared.globalLibrary != nil else {
            metadataSaveMessage = "No library"
            return
        }
        guard let entityId = entity.id else {
            metadataSaveMessage = "Entity ID missing"
            return
        }
        let trimmed = metadataJSON.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data),
              let dictAny = json as? [String: Any]
        else {
            metadataSaveMessage = "Invalid JSON object"
            return
        }
        guard let sendableMetadata = Self.makeSendableMetadata(dictAny) else {
            metadataSaveMessage = "Invalid JSON values"
            return
        }
        do {
            _ = try await entityService.patchEntity(entityId, metadata: sendableMetadata)
            metadataSaveMessage = "Saved"
        } catch {
            metadataSaveMessage = "Save failed"
        }
    }

    static func makeSendableMetadata(_ dict: [String: Any]) -> [String: any Sendable]? {
        var output: [String: any Sendable] = [:]
        for (key, value) in dict {
            guard let converted = makeSendableJSON(value) else { return nil }
            output[key] = converted
        }
        return output
    }

    static func makeSendableJSON(_ value: Any) -> (any Sendable)? {
        switch value {
        case let string as String:
            return string
        case let int as Int:
            return int
        case let double as Double:
            return double
        case let bool as Bool:
            return bool
        case let number as NSNumber:
            return number.doubleValue
        case let array as [Any]:
            return makeSendableArray(array)
        case let object as [String: Any]:
            return makeSendableMetadata(object)
        case _ as NSNull:
            return nil as String?
        default:
            return nil
        }
    }

    private static func makeSendableArray(_ array: [Any]) -> [any Sendable]? {
        var converted: [any Sendable] = []
        converted.reserveCapacity(array.count)
        for item in array {
            guard let sendable = makeSendableJSON(item) else { return nil }
            converted.append(sendable)
        }
        return converted
    }

    /// #3757 — header affordance that opens the external-authority link sheet.
    /// Lives on the extension (not the main struct body) so the entity detail
    /// view stays under its type-body budget; authority links are metadata,
    /// which is why this sits with the metadata editor.
    var authorityLinkButton: some View {
        Button {
            showAuthorityLinkSheet = true
        } label: {
            Label("Link authority", systemImage: "link.badge.plus")
                .font(.caption)
        }
        .buttonStyle(.bordered)
        .disabled(entity.id == nil)
        .help("Link this entity to an external authority (Wikidata, VIAF, Library of Congress)")
    }
}

// MARK: - External authority link (#3757)

/// Search external authorities (Wikidata / VIAF / LoC) and link one to this
/// entity. All endpoint access goes through `EntityStore` (observable-data-
/// layer): this sheet only reads the returned candidates and dispatches the
/// refresh/link actions — it never calls a service directly. Authority links
/// live in the entity's metadata (`authority_links`), which is why this sits
/// alongside the metadata editor.
struct EntityAuthorityLinkSheet: View {
    @Environment(\.dismiss) private var dismiss
    let entity: Components.Schemas.KnowledgeEntity
    let entityStore: EntityStore

    @State private var query: String
    @State private var candidates: [AuthorityCandidate] = []
    @State private var isSearching = false
    @State private var statusMessage: String?
    @State private var linkedIds: Set<String> = []

    init(entity: Components.Schemas.KnowledgeEntity, entityStore: EntityStore) {
        self.entity = entity
        self.entityStore = entityStore
        _query = State(initialValue: entity.canonicalName)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Link to external authority")
                .font(.headline)
            Text("Search Wikidata, VIAF, and the Library of Congress, then link a record to “\(entity.canonicalName)”.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                TextField("Search term", text: $query)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await search() } }
                Button("Search") { Task { await search() } }
                    .disabled(query.trimmingCharacters(in: .whitespaces).isEmpty || isSearching)
            }

            if isSearching {
                ProgressView().frame(maxWidth: .infinity)
            } else if let statusMessage {
                Text(statusMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            List(candidates) { candidate in
                candidateRow(candidate)
            }
            .frame(minHeight: 200)

            HStack {
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 520, height: 460)
    }

    @ViewBuilder
    private func candidateRow(_ candidate: AuthorityCandidate) -> some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(candidate.label).font(.body)
                Text("\(candidate.authority.uppercased()) · \(candidate.authorityId)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let description = candidate.description, !description.isEmpty {
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            Spacer()
            if linkedIds.contains(candidate.id) {
                Label("Linked", systemImage: "checkmark.circle.fill")
                    .labelStyle(.iconOnly)
                    .foregroundStyle(.green)
            } else {
                Button("Link") { Task { await link(candidate) } }
            }
        }
    }

    private func search() async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSearching = true
        statusMessage = nil
        defer { isSearching = false }
        do {
            candidates = try await entityStore.refreshAuthorityCandidates(query: trimmed)
            if candidates.isEmpty {
                statusMessage = "No authority records found for “\(trimmed)”."
            }
        } catch {
            candidates = []
            statusMessage = "Search failed: \(error.localizedDescription)"
        }
    }

    private func link(_ candidate: AuthorityCandidate) async {
        guard let entityId = entity.id else {
            statusMessage = "This entity has no id yet — save it before linking."
            return
        }
        do {
            try await entityStore.linkAuthority(
                entityId: entityId,
                authority: candidate.authority,
                authorityId: candidate.authorityId
            )
            linkedIds.insert(candidate.id)
        } catch {
            statusMessage = "Link failed: \(error.localizedDescription)"
        }
    }
}
