import FicheroAPIClient
import SwiftUI

// MARK: - Entities table view (the node-model build: an entity flows through the library table)

/// Renders the folder's (or library's) ENTITIES as a native, sortable table —
/// name · type · #claims · authority · curation — the entity half of the
/// node-model IA. Shows ALL entities, duplicates and messy NER included: the demo
/// point is that they are visible AND curatable in place (the machine extracts
/// everything; the scholar curates it). The row context menu wires the EXISTING
/// curation services (bless / reject / retype / merge / delete) — nothing new.
///
/// Same reuse contract as the claims table: rows carry the SAME
/// `LibraryOutlineNode.entityItem` identity the document outline mints and write
/// the SAME `selection` set; a single-row click opens the entity's detail/editor.
struct EntitiesTableView: View {
    struct Item: Identifiable {
        let node: LibraryOutlineNode
        let entity: Components.Schemas.KnowledgeEntity
        let values: EntityTableRow
        var id: String { node.id }
    }

    /// The curation / navigation actions, all backed by existing services in the
    /// host. Kept as a struct so the view's argument list stays legible.
    struct Actions {
        /// Single-row click: focus the entity and open its detail/editor.
        var open: (Components.Schemas.KnowledgeEntity) -> Void
        /// Bless (verified) / Reject / Mark unreviewed — via EntityStore.setCuration.
        var setCuration: ([Components.Schemas.KnowledgeEntity], EntityTableRow.Curation) -> Void
        /// Retype to an EntityType raw value — via EntityStore.reclassify.
        var setType: ([Components.Schemas.KnowledgeEntity], String) -> Void
        /// Merge duplicates — via EntityStore.merge (host picks the survivor).
        var merge: ([Components.Schemas.KnowledgeEntity]) -> Void
        /// Delete — via EntityStore.delete.
        var delete: ([Components.Schemas.KnowledgeEntity]) -> Void
    }

    let items: [Item]
    @Binding var selection: Set<String>
    let isLoading: Bool
    let emptyMessage: String
    let actions: Actions

    /// The retype options — the EntityType-Output cases, minus the current one is
    /// left to the user's judgement (retyping to the same type is a harmless no-op).
    /// A named `Identifiable` type, not a tuple: SwiftUI's `ForEach(_:id:)` needs a
    /// key path, and Swift has no key paths to tuple elements.
    private struct TypeOption: Identifiable {
        let raw: String
        let label: String
        var id: String { raw }
    }

    private static let typeOptions: [TypeOption] = [
        TypeOption(raw: "person", label: "Person"),
        TypeOption(raw: "location", label: "Location"),
        TypeOption(raw: "organization", label: "Organization"),
        TypeOption(raw: "event", label: "Event"),
        TypeOption(raw: "concept", label: "Concept"),
        TypeOption(raw: "citation", label: "Citation"),
        TypeOption(raw: "other", label: "Other")
    ]

    @State private var sortOrder: [KeyPathComparator<Item>] = [
        KeyPathComparator(\Item.values.name, order: .forward)
    ]

    private var sortedItems: [Item] { items.sorted(using: sortOrder) }

    var body: some View {
        Group {
            if isLoading && items.isEmpty {
                loadingState
            } else if items.isEmpty {
                emptyState
            } else {
                table
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var table: some View {
        Table(sortedItems, selection: $selection, sortOrder: $sortOrder) {
            TableColumn("Name", value: \.values.name) { item in
                Label(item.values.name, systemImage: "person.crop.circle").font(.body).lineLimit(1)
            }
            .width(min: 150, ideal: 220)

            TableColumn("Type", value: \.values.type) { item in
                Text(item.values.type).font(.callout).foregroundStyle(.secondary).lineLimit(1)
            }
            .width(min: 90, ideal: 120)

            TableColumn("Claims", value: \.values.claimCount) { item in
                Text("\(item.values.claimCount)").font(.callout.monospacedDigit()).foregroundStyle(.secondary)
            }
            .width(min: 60, ideal: 80)

            TableColumn("Authority", value: \.values.authority) { item in
                if item.values.authority.isEmpty {
                    Text("—").font(.callout).foregroundStyle(.tertiary)
                } else {
                    Label(item.values.authority, systemImage: "link")
                        .font(.callout).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            .width(min: 120, ideal: 170)

            TableColumn("Curation", value: \.values.curation.rawValue) { item in
                EntityTableCurationBadge(curation: item.values.curation)
            }
            .width(min: 90, ideal: 110)
        }
        .tableStyle(.inset)
        #if os(macOS)
        .alternatingRowBackgrounds()
        #endif
        .contextMenu(forSelectionType: String.self) { ids in
            curationMenu(for: ids)
        }
        .onChange(of: selection) { _, newSelection in
            guard newSelection.count == 1,
                  let id = newSelection.first,
                  let item = items.first(where: { $0.id == id }) else { return }
            actions.open(item.entity)
        }
    }

    /// The right-click curation menu, over the clicked/selected entities. Reuses
    /// the existing services through the host's action closures.
    @ViewBuilder
    private func curationMenu(for ids: Set<String>) -> some View {
        let targets = items.filter { ids.contains($0.id) }.map(\.entity)
        if !targets.isEmpty {
            Button { actions.setCuration(targets, .blessed) } label: {
                Label("Bless (verified)", systemImage: "checkmark.seal")
            }
            Button(role: .destructive) { actions.setCuration(targets, .rejected) } label: {
                Label("Reject", systemImage: "xmark.bin")
            }
            Button { actions.setCuration(targets, .unreviewed) } label: {
                Label("Mark unreviewed", systemImage: "arrow.uturn.backward")
            }
            Menu("Set type") {
                ForEach(Self.typeOptions) { option in
                    Button(option.label) { actions.setType(targets, option.raw) }
                }
            }
            if targets.count >= 2 {
                Button { actions.merge(targets) } label: {
                    Label("Merge \(targets.count) duplicates", systemImage: "arrow.triangle.merge")
                }
            }
            Divider()
            Button(role: .destructive) { actions.delete(targets) } label: {
                Label(targets.count == 1 ? "Delete entity" : "Delete \(targets.count) entities", systemImage: "trash")
            }
        }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading entities…").font(.callout).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "person.2").font(.largeTitle).foregroundStyle(.secondary)
            Text(emptyMessage)
                .font(.callout).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).frame(maxWidth: 420)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

/// The entity curation lozenge — the honesty layer. Blessed reads confident
/// (green), rejected is struck (red), unreviewed is the machine's raw output
/// (muted), merged is spent.
/// Curation badge for the entities TABLE (distinct from the inspector's
/// `EntityCurationBadge`, which takes an `EntityCurationState`; this one maps
/// the table's richer `EntityTableRow.Curation` incl. `.merged`).
struct EntityTableCurationBadge: View {
    let curation: EntityTableRow.Curation

    var body: some View {
        Text(curation.rawValue)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.16), in: Capsule())
            .foregroundStyle(color)
    }

    private var color: Color {
        switch curation {
        case .blessed: return .green
        case .rejected: return .red
        case .merged: return .gray
        case .unreviewed: return .orange
        }
    }
}
