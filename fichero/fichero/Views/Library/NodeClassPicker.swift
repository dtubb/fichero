import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Curated-items section (#1570 Phase 1)

/// Workspace curated-items section for the document inspector. Shown only when
/// the selected document is a workspace folder (`doc.isWorkspace == true`).
/// Loads the folder's curated items from `GET .../workspace/items` and renders
/// one row per item with a `NodeClassPicker` chip. Conservative, least-invasive
/// placement: a single `Section` folded into the existing inspector `Form`,
/// not a rewrite of LibraryView. (#1570)
struct WorkspaceCuratedItemsSection: View {
    let folderId: String

    @Environment(DocumentService.self) private var documentService
    @State private var service = WorkspacePickerService()
    @State private var items: [WorkspaceCuratedItem] = []
    @State private var nodeClasses: [Components.Schemas.ClassificationValue] = []
    @State private var isLoading = false
    @State private var loadError: String?

    private let logger = Logger(
        subsystem: "app.fichero.fichero",
        category: "WorkspaceCuratedItemsSection"
    )

    var body: some View {
        Group {
            if isLoading {
                HStack { ProgressView().controlSize(.small); Text("Loading items…") }
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if let loadError {
                Text(loadError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if items.isEmpty {
                Text("No curated items yet")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .help("Add documents to this workspace to classify them with a node class")
            } else {
                ForEach(items) { item in
                    itemRow(item)
                }
            }
        }
        .task(id: folderId) { await load() }
    }

    @ViewBuilder
    private func itemRow(_ item: WorkspaceCuratedItem) -> some View {
        LabeledContent {
            NodeClassPicker(
                folderId: folderId,
                item: item,
                nodeClasses: nodeClasses,
                onAssign: { newKey in
                    if let idx = items.firstIndex(where: { $0.id == item.id }) {
                        items[idx] = item.withNodeClass(newKey)
                    }
                }
            )
        } label: {
            Text(itemLabel(item))
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }

    private func itemLabel(_ item: WorkspaceCuratedItem) -> String {
        let type = item.targetType.isEmpty ? "Item" : item.targetType.capitalized
        return "\(type) · \(item.targetId.prefix(8))"
    }

    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        if let svc = LibraryManager.shared.globalLibrary?.entityService {
            nodeClasses = (try? await svc.listNodeClasses()) ?? []
        }
        do {
            items = try await service.loadCuratedItems(
                folderId: folderId,
                documentService: documentService
            )
        } catch {
            loadError = error.localizedDescription
            logger.error("loadCuratedItems failed: \(error.localizedDescription)")
        }
    }
}

// MARK: - Node-class picker (#1570)

/// Tinderbox-style node-class picker for one workspace curated item. Modelled
/// exactly on `DocumentPrototypePicker` — a `Menu` listing the node_class
/// classification values, showing the reused `PrototypeBadge` chip when one is
/// assigned, and PATCHing the item via `WorkspacePickerService.setNodeClass`
/// on selection. (#1570)
struct NodeClassPicker: View {
    let folderId: String
    let item: WorkspaceCuratedItem
    let nodeClasses: [Components.Schemas.ClassificationValue]
    /// Called with the newly assigned key (nil = cleared) so the parent can
    /// keep its row in sync without a full reload.
    var onAssign: (String?) -> Void = { _ in }

    @State private var selectedKey: String?
    @State private var isAssigning = false
    @Environment(DocumentService.self) private var documentService
    @State private var service = WorkspacePickerService()

    var body: some View {
        if nodeClasses.isEmpty && !isAssigning {
            Text("No classes defined")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .help("Define node classes in Settings → Classification to classify workspace items")
        } else {
            Menu {
                Button("None") {
                    Task { await assign(nil) }
                }
                Divider()
                ForEach(nodeClasses, id: \.key) { proto in
                    Button {
                        Task { await assign(proto.key) }
                    } label: {
                        Label {
                            Text(proto.label)
                        } icon: {
                            if selectedKey == proto.key {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    if isAssigning {
                        ProgressView().controlSize(.mini)
                    }
                    if let key = selectedKey,
                       let proto = nodeClasses.first(where: { $0.key == key }) {
                        PrototypeBadge(proto: proto)
                    } else {
                        Text("None")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Image(systemName: "chevron.up.chevron.down")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .buttonStyle(.plain)
            .help("Assign a node class to this workspace item")
            .task { selectedKey = item.nodeClass }
        }
    }

    private func assign(_ key: String?) async {
        isAssigning = true
        defer { isAssigning = false }
        do {
            _ = try await service.setNodeClass(
                folderId: folderId,
                item: item,
                nodeClass: key,
                documentService: documentService
            )
            selectedKey = key
            onAssign(key)
        } catch {
            // Leave the previous selection in place on failure.
        }
    }
}
