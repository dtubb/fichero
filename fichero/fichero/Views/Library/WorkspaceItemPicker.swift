import Foundation
import OSLog
import SwiftUI

// MARK: - Service

/// Lightweight, self-contained service backing the Add-to-Workspace picker.
/// Mirrors the `NoteService` convention (raw `URLSession` + `addEngineAuth`)
/// so the picker needs no `APIClient`/library plumbing. (#1494)
///
/// Two calls only:
///   * `loadWorkspaceFolders()` — GET /api/documents?doc_type=folder, kept to
///     the `is_workspace` ones (Thing 2 surfaces, per #1487).
///   * `addToWorkspace(folderId:targetId:)` — PATCH /api/documents/{id}/workspace
///     appending one `curated_item` alias. The source document is never moved.
@MainActor
final class WorkspacePickerService: ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkspacePickerService")
    private let documentsBase = "http://127.0.0.1:8765/api/documents"

    @Published var folders: [WorkspaceFolderItem] = []
    @Published var isLoading = false
    @Published var error: String?

    func loadWorkspaceFolders() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            guard var comps = URLComponents(string: documentsBase) else { return }
            comps.queryItems = [URLQueryItem(name: "doc_type", value: "folder")]
            guard let url = comps.url else { return }
            var req = URLRequest(url: url)
            req.addEngineAuth()
            let (data, _) = try await URLSession.shared.data(for: req)
            let resp = try JSONDecoder().decode(WorkspaceFolderListResponse.self, from: data)
            folders = resp.items
                .filter { $0.isWorkspace && ($0.docType == "folder") }
                .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        } catch {
            self.error = error.localizedDescription
            logger.error("loadWorkspaceFolders failed: \(error.localizedDescription)")
        }
    }

    /// Append `targetId` to `folderId`'s curated items as an alias. Returns
    /// the new curated-item count on success.
    @discardableResult
    func addToWorkspace(folderId: String, targetId: String) async throws -> Int {
        guard let url = URL(string: "\(documentsBase)/\(folderId)/workspace") else {
            throw WorkspacePickerError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = "PATCH"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addEngineAuth()
        let item = WorkspaceCuratedItemAdd(
            id: UUID().uuidString,
            targetType: "Document",
            targetId: targetId,
            role: "curated_item"
        )
        req.httpBody = try JSONEncoder().encode(WorkspacePatchBody(add: [item]))
        let (data, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw WorkspacePickerError.server(http.statusCode)
        }
        let resp = try JSONDecoder().decode(WorkspaceItemsCountResponse.self, from: data)
        return resp.count
    }
}

enum WorkspacePickerError: LocalizedError {
    case invalidURL
    case server(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "Invalid URL"
        case let .server(code): "Server returned \(code)"
        }
    }
}

// MARK: - Wire models

/// Minimal projection of a document row — only the fields the picker needs.
struct WorkspaceFolderItem: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let docType: String
    let isWorkspace: Bool

    enum CodingKeys: String, CodingKey {
        case id, name
        case docType = "doc_type"
        case isWorkspace = "is_workspace"
    }

    // Tolerate older rows that predate the is_workspace column.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = (try? container.decode(String.self, forKey: .name)) ?? "Untitled"
        docType = (try? container.decode(String.self, forKey: .docType)) ?? "folder"
        isWorkspace = (try? container.decode(Bool.self, forKey: .isWorkspace)) ?? false
    }
}

private struct WorkspaceFolderListResponse: Codable {
    let items: [WorkspaceFolderItem]
    let count: Int
}

private struct WorkspaceCuratedItemAdd: Encodable {
    let id: String
    let targetType: String
    let targetId: String
    let role: String

    enum CodingKeys: String, CodingKey {
        case id, role
        case targetType = "target_type"
        case targetId = "target_id"
    }
}

private struct WorkspacePatchBody: Encodable {
    let add: [WorkspaceCuratedItemAdd]
}

private struct WorkspaceItemsCountResponse: Codable {
    let count: Int
}

// MARK: - View

/// Sheet that lets the user add a document to one of their workspace folders
/// as a curated-item alias. Reached from the "Add to Workspace…" library row
/// context menu. The source document is *aliased*, never moved (#1487). (#1494)
struct WorkspaceItemPicker: View {
    /// The document being added to a workspace.
    let document: Document

    @Environment(\.dismiss) private var dismiss
    @StateObject private var service = WorkspacePickerService()
    @State private var addingFolderId: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            content
        }
        .frame(width: 420, height: 460)
        .task { await service.loadWorkspaceFolders() }
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
                    .fill(Color(.quaternaryLabelColor).opacity(0.12))
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
                Task { await service.loadWorkspaceFolders() }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func add(to folder: WorkspaceFolderItem) async {
        addingFolderId = folder.id
        defer { addingFolderId = nil }
        do {
            _ = try await service.addToWorkspace(folderId: folder.id, targetId: document.id)
            dismiss()
        } catch {
            service.error = error.localizedDescription
        }
    }
}
