import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Document Entities Tab

private let inspectorEntitiesLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "DocumentInspectorEntitiesTab"
)

struct DocumentInspectorEntitiesTab: View {
    let documentId: String
    let entityService: EntityServiceGenerated
    var onEntitySelect: ((String) -> Void)?

    @State private var entities: [Components.Schemas.KnowledgeEntity] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @AppStorage("inspector.entities.hiddenKinds") private var hiddenKindsCSV: String = ""

    private var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    private var grouped: [(EntityKind, [Components.Schemas.KnowledgeEntity])] {
        let grouped = Dictionary(grouping: entities) { entity in
            EntityKind(apiType: entity.entityType) ?? .other
        }
        return EntityKind.displayOrder.compactMap { kind in
            guard !hiddenKinds.contains(kind), let items = grouped[kind], !items.isEmpty else {
                return nil
            }
            return (kind, items.sorted { lhs, rhs in
                lhs.canonicalName.localizedCaseInsensitiveCompare(rhs.canonicalName) == .orderedAscending
            })
        }
    }

    private var hasActiveKindFilter: Bool {
        !hiddenKinds.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                header

                if isLoading {
                    ProgressView().padding(.vertical, 8)
                } else if let loadError {
                    Label(loadError, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                } else if entities.isEmpty {
                    Text("No entities for this document yet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if grouped.isEmpty {
                    emptyVisibleGroupsState
                } else {
                    ForEach(grouped, id: \.0) { kind, items in
                        entityKindSection(kind: kind, entities: items)
                    }
                }
            }
            .padding()
        }
        .task(id: documentId) { await loadEntities() }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("\(entities.count) entities")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            filterMenu
            Button {
                Task { await loadEntities() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload entities")
        }
    }

    @ViewBuilder
    private var emptyVisibleGroupsState: some View {
        if hasActiveKindFilter {
            VStack(alignment: .leading, spacing: 6) {
                Text("Loaded \(entities.count) entities, but the current filter hides every kind.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Show all kinds") {
                    hiddenKindsCSV = ""
                }
                .buttonStyle(.link)
                .font(.caption)
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    "Loaded \(entities.count) entities, but none mapped into a visible section.",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)

                entityKindSection(kind: .other, entities: entities)
            }
        }
    }

    private var filterMenu: some View {
        Menu {
            ForEach(EntityKind.displayOrder, id: \.self) { kind in
                let isHidden = hiddenKinds.contains(kind)
                Button {
                    setHidden(kind, hidden: !isHidden)
                } label: {
                    Label(kind.label, systemImage: isHidden ? "" : "checkmark")
                }
            }
            Divider()
            Button("Show all") { hiddenKindsCSV = "" }
            Button("Hide all") {
                hiddenKindsCSV = EntityKind.displayOrder
                    .map(\.rawValue)
                    .sorted()
                    .joined(separator: ",")
            }
        } label: {
            Image(systemName: hiddenKinds.isEmpty
                    ? "line.3.horizontal.decrease.circle"
                    : "line.3.horizontal.decrease.circle.fill")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter entity kinds")
    }

    private func entityKindSection(
        kind: EntityKind,
        entities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("\(kind.label.uppercased()) \(entities.count)", systemImage: kind.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            ForEach(entities, id: \.stableInspectorId) { entity in
                entityRow(entity, kind: kind)
            }
        }
    }

    private func entityRow(
        _ entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) -> some View {
        Button {
            if let id = entity.id {
                onEntitySelect?(id)
            } else {
                postSearch(for: entity, kind: kind)
            }
        } label: {
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(entity.canonicalName)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.primary)
                    if let count = entity.sourceDocumentIds?.count, count > 1 {
                        Text("\(count) sources")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                }
                if let aliases = entity.aliases, !aliases.isEmpty {
                    Text(aliases.prefix(3).joined(separator: ", "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if let description = entity.description, !description.isEmpty {
                    Text(description)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.accentColor.opacity(0.06))
            )
        }
        .buttonStyle(.plain)
        .help("Inspect \(entity.canonicalName)")
    }

    private func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    private func loadEntities() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let loaded = try await entityService.listInspectorEntitiesForDocument(
                documentId: documentId
            )
            inspectorEntitiesLogger.debug(
                "Loaded \(loaded.count, privacy: .public) inspector entities for \(documentId, privacy: .public)"
            )
            entities = loaded
        } catch is CancellationError {
            // Superseded by a newer document selection.
        } catch {
            inspectorEntitiesLogger.error(
                "Failed to load inspector entities for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            loadError = "Couldn't load entities: \(error.localizedDescription)"
            entities = []
        }
    }

    private func postSearch(
        for entity: Components.Schemas.KnowledgeEntity,
        kind: EntityKind
    ) {
        NotificationCenter.default.post(
            name: .ficheroEntitySearchRequested,
            object: nil,
            userInfo: [
                "name": entity.canonicalName,
                "entityType": kind.searchScope
            ]
        )
    }
}

extension Components.Schemas.KnowledgeEntity {
    var stableInspectorId: String {
        id ?? "\(entityType?.rawValue ?? "other"):\(canonicalName)"
    }
}
