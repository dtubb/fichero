import FicheroAPIClient
import Foundation
import Observation
import OSLog
import SwiftUI

// MARK: - Service

/// Lightweight state holder backing the Add-to-Workspace picker.
/// Transport flows through `DocumentService` so every request uses the
/// generated OpenAPI client and the active library path from the window's
/// `LibraryReference`.
@MainActor
@Observable
final class WorkspacePickerService {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkspacePickerService")

    var folders: [WorkspaceFolderItem] = []
    var isLoading = false
    var error: String?

    func loadWorkspaceFolders(documentService: DocumentService) async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            let workspaces = try await documentService.getWorkspaces()
            folders = workspaces
                .filter { $0.docType == .folder }
                .map(WorkspaceFolderItem.init(document:))
                .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        } catch {
            self.error = error.localizedDescription
            logger.error("loadWorkspaceFolders failed: \(error.localizedDescription)")
        }
    }

    /// Append `targetId` to `folderId`'s curated items as an alias. Returns
    /// the new curated-item count on success.
    @discardableResult
    func addToWorkspace(
        folderId: String,
        targetId: String,
        documentService: DocumentService
    ) async throws -> Int {
        let item = Components.Schemas.WorkspaceCuratedItem(
            id: UUID().uuidString,
            targetType: "Document",
            targetId: targetId,
            role: "curated_item"
        )
        let resp = try await documentService.patchWorkspaceItems(folderId: folderId, itemsToAdd: [item])
        return resp.count
    }

    /// Load the curated items for a workspace folder, resolving each alias.
    /// First caller of `GET /api/documents/{id}/workspace/items` (#1570).
    func loadCuratedItems(
        folderId: String,
        documentService: DocumentService
    ) async throws -> [WorkspaceCuratedItem] {
        let resp = try await documentService.getWorkspaceItems(folderId: folderId)
        return resp.items.map(WorkspaceCuratedItem.init(payload:))
    }

    /// Set (or clear) the Tinderbox-style `node_class` on one curated item
    /// and PATCH it back. The backend's `add` path replaces the item by id,
    /// so we resend the *whole* item (id/target/role/notes) with the new
    /// node_class — sending a partial payload would wipe the other fields (#1570).
    @discardableResult
    func setNodeClass(
        folderId: String,
        item: WorkspaceCuratedItem,
        nodeClass: String?,
        documentService: DocumentService
    ) async throws -> Int {
        let add = Components.Schemas.WorkspaceCuratedItem(
            id: item.id,
            targetType: item.targetType,
            targetId: item.targetId,
            role: item.role ?? "curated_item",
            notes: item.notes,
            nodeClass: nodeClass
        )
        let resp = try await documentService.patchWorkspaceItems(folderId: folderId, itemsToAdd: [add])
        return resp.count
    }
}

// MARK: - Wire models

/// Minimal projection of a document row — only the fields the picker needs.
struct WorkspaceFolderItem: Identifiable, Hashable {
    let id: String
    let name: String
    let docType: String
    let isWorkspace: Bool

    init(document: Document) {
        id = document.id
        name = document.name
        docType = document.docType.rawValue
        isWorkspace = true
    }
}

/// Typed projection of a curated workspace item (#1570). Mirrors the backend
/// `WorkspaceCuratedItem` rows returned by `GET .../workspace/items`. Old
/// payloads that predate `node_class` decode cleanly — every optional field
/// tolerates absence.
struct WorkspaceCuratedItem: Decodable, Identifiable, Hashable {
    let id: String
    let targetType: String
    let targetId: String
    let role: String?
    let notes: String?
    let nodeClass: String?

    enum CodingKeys: String, CodingKey {
        case id, role, notes
        case targetType = "target_type"
        case targetId = "target_id"
        case nodeClass = "node_class"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        targetType = (try? container.decode(String.self, forKey: .targetType)) ?? ""
        targetId = (try? container.decode(String.self, forKey: .targetId)) ?? ""
        role = try? container.decodeIfPresent(String.self, forKey: .role)
        notes = try? container.decodeIfPresent(String.self, forKey: .notes)
        nodeClass = try? container.decodeIfPresent(String.self, forKey: .nodeClass)
    }

    private init(
        id: String, targetType: String, targetId: String,
        role: String?, notes: String?, nodeClass: String?
    ) {
        self.id = id
        self.targetType = targetType
        self.targetId = targetId
        self.role = role
        self.notes = notes
        self.nodeClass = nodeClass
    }

    init(payload: Components.Schemas.WorkspaceItemsResponse.ItemsPayloadPayload) {
        let values = payload.additionalProperties.value
        self.init(
            id: (values["id"] as? String) ?? UUID().uuidString,
            targetType: (values["target_type"] as? String) ?? "",
            targetId: (values["target_id"] as? String) ?? "",
            role: values["role"] as? String,
            notes: values["notes"] as? String,
            nodeClass: values["node_class"] as? String
        )
    }

    /// Returns a copy with `node_class` replaced — lets the picker update a row
    /// in place after a successful PATCH without a full reload.
    func withNodeClass(_ newValue: String?) -> WorkspaceCuratedItem {
        WorkspaceCuratedItem(
            id: id, targetType: targetType, targetId: targetId,
            role: role, notes: notes, nodeClass: newValue
        )
    }
}

// MARK: - View

/// Sheet that lets the user add a document to one of their workspace folders
/// as a curated-item alias. Reached from the "Add to Workspace…" library row
/// context menu. The source document is *aliased*, never moved (#1487). (#1494)
struct WorkspaceItemPicker: View {
    /// The document being added to a workspace.
    let document: Document

    @Environment(\.dismiss) private var dismiss
    @Environment(DocumentService.self) private var documentService
    @State private var service = WorkspacePickerService()
    @State private var addingFolderId: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            content
        }
        .frame(width: 420, height: 460)
        .task { await service.loadWorkspaceFolders(documentService: documentService) }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Add to Workspace")
                    .font(.headline)
                Text(document.name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Button("Done") { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(12)
    }

    @ViewBuilder
    private var content: some View {
        if service.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = service.error {
            errorState(error)
        } else if service.folders.isEmpty {
            emptyState
        } else {
            folderList
        }
    }

    private var folderList: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                ForEach(service.folders) { folder in
                    folderRow(folder)
                }
            }
            .padding(10)
        }
    }

    @ViewBuilder
    private func folderRow(_ folder: WorkspaceFolderItem) -> some View {
        Button {
            Task { await add(to: folder) }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "square.grid.2x2")
                    .foregroundStyle(Color.accentColor)
                Text(folder.name)
                    .lineLimit(1)
                Spacer()
                if addingFolderId == folder.id {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: "plus.circle")
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(platformColor: .platformQuaternaryLabel).opacity(0.12))
            )
        }
        .buttonStyle(.plain)
        .disabled(addingFolderId != nil)
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "tray")
                .font(.largeTitle)
                .foregroundStyle(.tertiary)
            Text("No workspaces yet")
                .foregroundStyle(.secondary)
            Text("Mark a folder as a workspace to collect items into it.")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") {
                Task { await service.loadWorkspaceFolders(documentService: documentService) }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func add(to folder: WorkspaceFolderItem) async {
        addingFolderId = folder.id
        defer { addingFolderId = nil }
        do {
            _ = try await service.addToWorkspace(
                folderId: folder.id,
                targetId: document.id,
                documentService: documentService
            )
            dismiss()
        } catch {
            service.error = error.localizedDescription
        }
    }
}
