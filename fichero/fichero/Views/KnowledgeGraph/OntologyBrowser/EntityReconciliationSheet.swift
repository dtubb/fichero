import FicheroAPIClient
import SwiftUI

/// Reconciliation scope (#3318): the USER explicitly chooses where to look for
/// duplicate entities. Within-folder and within-library ship now; cross-library
/// (#3527) and external-authority / Wikidata (#3528) are deferred and shown
/// disabled ("coming soon") so the full scope ladder is visible.
enum EntityReconciliationScope: String, CaseIterable, Identifiable {
    case folder
    case library
    case crossLibrary
    case external

    var id: String { rawValue }

    var title: String {
        switch self {
        case .folder: return "Folder"
        case .library: return "Library"
        case .crossLibrary: return "Cross-Library"
        case .external: return "External"
        }
    }

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .library: return "books.vertical"
        case .crossLibrary: return "square.stack.3d.up"
        case .external: return "globe"
        }
    }

    /// Folder + Library are implemented; the wider scopes are deferred.
    var isAvailable: Bool { self == .folder || self == .library }

    /// Tooltip for the disabled scopes so the deferral is discoverable.
    var help: String {
        switch self {
        case .folder: return "Find duplicate entities within this document / folder"
        case .library: return "Find duplicate entities across the whole library"
        case .crossLibrary: return "Cross-library reconciliation — coming soon (#3527)"
        case .external: return "External authority (Wikidata / Wikipedia) — coming soon (#3528)"
        }
    }
}

/// A set of entities the reconciliation pass flagged as likely duplicates. The
/// user picks the survivor; the rest merge into it.
struct EntityReconciliationGroup: Identifiable {
    let id: String
    let entities: [Components.Schemas.KnowledgeEntity]
}

/// User-driven entity reconciliation (#3318). The user chooses a scope, the
/// sheet lists duplicate-entity candidate groups for that scope, and each group
/// merges via the shared `EntityStore.merge` action (audited + undoable) — the
/// same merge the per-entity "Possible Duplicates" affordance uses (#3317). The
/// system never merges automatically.
struct EntityReconciliationSheet: View {
    /// The document/folder in focus — the target of `.folder` scope.
    let documentId: String

    @Environment(EntityStore.self) private var entityStore
    @Environment(\.dismiss) private var dismiss

    @State private var scope: EntityReconciliationScope = .folder
    @State private var groups: [EntityReconciliationGroup] = []
    @State private var isLoading = false
    @State private var message: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            scopeBar
            Divider()
            content
            Divider()
            footer
        }
        .frame(minWidth: 420, minHeight: 440)
        .task(id: scope) { await load() }
    }

    private var header: some View {
        HStack {
            Label("Reconcile Entities", systemImage: "arrow.triangle.merge")
                .font(.headline)
            if isLoading { ProgressView().controlSize(.small) }
            Spacer()
        }
        .padding(12)
    }

    /// The scope ladder as a row of selectable chips; cross-library / external
    /// render disabled ("coming soon") but visible (#3318).
    private var scopeBar: some View {
        HStack(spacing: 8) {
            ForEach(EntityReconciliationScope.allCases) { option in
                Button {
                    scope = option
                } label: {
                    Label(option.title, systemImage: option.icon)
                        .font(.caption)
                }
                .buttonStyle(.bordered)
                .tint(scope == option ? .accentColor : nil)
                .disabled(!option.isAvailable)
                .help(option.help)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var content: some View {
        if let message {
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
        }
        if groups.isEmpty && !isLoading {
            ContentUnavailableView(
                "No likely duplicates",
                systemImage: "checkmark.seal",
                description: Text("No duplicate entities were found in the \(scope.title.lowercased()) scope.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(groups) { group in
                groupSection(group)
            }
            .listStyle(.inset)
        }
    }

    @ViewBuilder
    private func groupSection(_ group: EntityReconciliationGroup) -> some View {
        Section {
            ForEach(group.entities, id: \.id) { entity in
                HStack(spacing: 8) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(entity.canonicalName).font(.body).lineLimit(1)
                        if let type = entity.entityType?.rawValue {
                            Text(type.capitalized).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    Spacer(minLength: 8)
                    Button("Keep") { merge(group: group, survivor: entity) }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .help("Keep \"\(entity.canonicalName)\" and merge the rest of this group into it")
                }
            }
        } header: {
            Text("\(group.entities.count) possible duplicates")
                .font(.caption)
        }
    }

    private var footer: some View {
        HStack {
            Text(groups.isEmpty ? "" : "\(groups.count) group\(groups.count == 1 ? "" : "s")")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Done") { dismiss() }
                .keyboardShortcut(.defaultAction)
        }
        .padding(12)
    }

    // MARK: - Data

    /// Load the scope's entities and group likely duplicates.
    ///
    /// INTERIM candidate source: normalized-name grouping over the scope's
    /// entities (works today with data the app already holds). codex's scoped
    /// reconciliation endpoint (#3318 engine) — semantic/fuzzy matching with
    /// confidence — will replace `Self.groupDuplicates` here once it lands in
    /// the OpenAPI client; the scope picker + merge UI stay as-is.
    private func load() async {
        guard scope.isAvailable else { groups = []; return }
        isLoading = true
        defer { isLoading = false }
        message = nil
        let entities: [Components.Schemas.KnowledgeEntity]
        switch scope {
        case .folder:
            await entityStore.loadEntities(forDocument: documentId)
            entities = entityStore.entitiesByDocumentId[documentId] ?? []
        case .library:
            await entityStore.loadEntities(force: false)
            entities = entityStore.libraryEntities
        case .crossLibrary, .external:
            entities = []
        }
        groups = Self.groupDuplicates(entities)
    }

    /// Group entities whose normalized canonical name (or a shared alias)
    /// collides — the cheap, exact-ish duplicate signal. Exposed for tests.
    static func groupDuplicates(
        _ entities: [Components.Schemas.KnowledgeEntity]
    ) -> [EntityReconciliationGroup] {
        var byKey: [String: [Components.Schemas.KnowledgeEntity]] = [:]
        for entity in entities {
            let key = normalizedKey(entity.canonicalName)
            guard !key.isEmpty else { continue }
            byKey[key, default: []].append(entity)
        }
        return byKey
            .filter { $0.value.count >= 2 }
            .map { EntityReconciliationGroup(id: $0.key, entities: $0.value) }
            .sorted { $0.entities.count > $1.entities.count }
    }

    static func normalizedKey(_ name: String) -> String {
        name.nfcNormalized
            .lowercased()
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func merge(group: EntityReconciliationGroup, survivor: Components.Schemas.KnowledgeEntity) {
        guard let survivorId = survivor.id else { return }
        let absorbed = group.entities.compactMap(\.id).filter { $0 != survivorId }
        guard !absorbed.isEmpty else { return }
        Task {
            do {
                try await entityStore.merge(absorbedIds: absorbed, into: survivorId)
                message = "Merged \(absorbed.count) into \"\(survivor.canonicalName)\"."
                await load()
            } catch {
                message = "Merge failed: \(error.localizedDescription)"
            }
        }
    }
}
