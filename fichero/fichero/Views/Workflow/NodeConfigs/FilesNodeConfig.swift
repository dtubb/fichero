import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "FilesNodeConfig")

/// Configuration view for files node
struct FilesNodeConfig: View {
    @Binding var node: WorkflowNode

    @Environment(DocumentStore.self) var documentStore: DocumentStore

    @State private var selectedFileIds: [String] = []
    @State private var showFilePicker = false
    @State private var stagedPickerSelection: Set<String> = []
    @State private var fileSearchText = ""
    @State private var expandedFolderIds: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if selectedFileIds.isEmpty {
                selectionBanner
            } else {
                Text("Pinned Files")
                    .font(.caption)
                    .foregroundColor(.secondary)
                VStack(spacing: 4) {
                    ForEach(selectedFileIds, id: \.self) { fileId in
                        fileRow(fileId: fileId)
                    }
                    dropZoneView
                }
            }

            if showFilePicker {
                filePickerPanel
            }
        }
        .task {
            if documentStore.collections.isEmpty {
                await documentStore.loadCollections()
            }
        }
        .onAppear {
            loadInitialState()
        }
    }
}

private extension FilesNodeConfig {
    var selectionBanner: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "cursorarrow.rays")
                    .foregroundStyle(.teal)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Uses library selection at run time")
                        .font(.caption)
                        .fontWeight(.medium)
                    Text("Select documents in the library before running.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(8)
            .background(.teal.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 6))

            Button {
                showFilePickerSheet()
            } label: {
                Label("Pin specific files…", systemImage: "pin")
                    .font(.caption)
            }
            .buttonStyle(.borderless)
            .foregroundStyle(.secondary)
        }
    }

    var dropZoneView: some View {
        RoundedRectangle(cornerRadius: 6)
            .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [5]))
            .foregroundColor(.secondary)
            .frame(height: 44)
            .overlay(
                HStack {
                    Image(systemName: "plus.circle")
                    Text("Drop files here or click to select")
                        .font(.caption)
                }
                .foregroundColor(.secondary)
            )
            .onDrop(of: [.plainText], isTargeted: nil) { providers in
                handleFileDrop(providers)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                showFilePickerSheet()
            }
    }

    var filePickerPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Select Files")
                .font(.caption)
                .foregroundColor(.secondary)

            TextField("Search files", text: $fileSearchText)
                .textFieldStyle(.roundedBorder)

            if availableDocuments.isEmpty {
                ContentUnavailableView(
                    "No Files Available",
                    systemImage: "doc",
                    description: Text("Import files in Library first.")
                )
            } else {
                List {
                    ForEach(rootFolders, id: \.id) { folder in
                        FolderSectionView(
                            folder: folder,
                            depth: 0,
                            ancestry: [],
                            filesByParentMap: filesByParentMap,
                            folderChildrenMap: folderChildrenMap,
                            expandedFolderIds: $expandedFolderIds,
                            stagedPickerSelection: stagedPickerSelection,
                            onToggle: togglePickerSelection
                        )
                    }

                    if let rootFiles = filesByParentMap[nil], !rootFiles.isEmpty {
                        Section("Root") {
                            ForEach(rootFiles, id: \.id) { doc in
                                FilePickerRowView(
                                    doc: doc,
                                    depth: 1,
                                    isSelected: stagedPickerSelection.contains(doc.id),
                                    onToggle: togglePickerSelection
                                )
                            }
                        }
                    }
                }
                .listStyle(.sidebar)
                .frame(minHeight: 160, maxHeight: 240)
                .cornerRadius(6)
            }

            HStack {
                Button("Cancel") {
                    showFilePicker = false
                }
                .buttonStyle(.borderless)

                Spacer()

                Button("Add") {
                    selectedFileIds = Array(stagedPickerSelection).sorted()
                    syncConfig()
                    showFilePicker = false
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(8)
        .background(Color(platformColor: .controlBackgroundColor))
        .cornerRadius(6)
    }

    @ViewBuilder
    func fileRow(fileId: String) -> some View {
        let docName =
            documentStore.collections.first(where: { $0.id == fileId })?.name
            ?? "Document \(fileId.prefix(8))..."

        HStack {
            Image(systemName: "doc")
                .foregroundColor(.secondary)
            Text(docName)
                .font(.caption)
                .lineLimit(1)
            Spacer()
            Button {
                removeFile(fileId)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(.controlBackgroundColor))
        .cornerRadius(4)
    }

}

// MARK: - FolderSectionView

/// Recursive folder-tree row for the file picker.
/// Extracted as a dedicated View struct so SwiftUI can structurally diff each
/// level without AnyView type-erasure defeating the diffing engine.
private struct FolderSectionView: View {
    let folder: Document
    let depth: Int
    let ancestry: Set<String>
    let filesByParentMap: [String?: [Document]]
    let folderChildrenMap: [String: [Document]]
    @Binding var expandedFolderIds: Set<String>
    let stagedPickerSelection: Set<String>
    let onToggle: (String) -> Void

    var body: some View {
        if ancestry.contains(folder.id) {
            EmptyView()
        } else {
            let nextAncestry = ancestry.union([folder.id])
            DisclosureGroup(
                isExpanded: Binding(
                    get: { expandedFolderIds.contains(folder.id) },
                    set: { isExpanded in
                        if isExpanded {
                            expandedFolderIds.insert(folder.id)
                        } else {
                            expandedFolderIds.remove(folder.id)
                        }
                    }
                )
            ) {
                if let directFiles = filesByParentMap[folder.id], !directFiles.isEmpty {
                    ForEach(directFiles, id: \.id) { doc in
                        FilePickerRowView(
                            doc: doc,
                            depth: depth + 1,
                            isSelected: stagedPickerSelection.contains(doc.id),
                            onToggle: onToggle
                        )
                    }
                }

                if let children = folderChildrenMap[folder.id] {
                    ForEach(children, id: \.id) { child in
                        FolderSectionView(
                            folder: child,
                            depth: depth + 1,
                            ancestry: nextAncestry,
                            filesByParentMap: filesByParentMap,
                            folderChildrenMap: folderChildrenMap,
                            expandedFolderIds: $expandedFolderIds,
                            stagedPickerSelection: stagedPickerSelection,
                            onToggle: onToggle
                        )
                    }
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: folder.name == "Inbox" ? "tray.fill" : "folder")
                        .foregroundStyle(.secondary)
                    Text(folder.name)
                        .lineLimit(1)
                        .foregroundStyle(.primary)
                    Spacer()
                }
                .padding(.vertical, 4)
                .padding(.leading, 4)
                .padding(.trailing, 6)
            }
            .disclosureGroupStyle(.automatic)
        }
    }
}

// MARK: - FilePickerRowView

/// Single selectable file row for the file picker.
/// Extracted to give FolderSectionView a concrete (non-AnyView) child type.
private struct FilePickerRowView: View {
    let doc: Document
    let depth: Int
    let isSelected: Bool
    let onToggle: (String) -> Void

    var body: some View {
        Button {
            onToggle(doc.id)
        } label: {
            HStack(spacing: 6) {
                Image(
                    systemName: isSelected
                        ? "checkmark.circle.fill"
                        : "circle"
                )
                .foregroundStyle(
                    isSelected
                        ? Color.accentColor
                        : Color.secondary
                )
                Image(systemName: doc.fileType?.icon ?? "doc")
                    .foregroundStyle(.secondary)
                Text(doc.name)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.vertical, 4)
            .padding(.leading, 6)
            .padding(.trailing, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(isSelected
                        ? Color.accentColor.opacity(0.12)
                        : Color.clear)
        )
    }
}

private extension FilesNodeConfig {
    var allFolders: [Document] {
        documentStore.collections
            .filter { $0.docType == .folder }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
    }

    var validFolderIds: Set<String> {
        Set(allFolders.map(\.id))
    }

    var availableDocuments: [Document] {
        let candidates = documentStore.collections
            .filter { $0.docType == .file }
            .filter { doc in
                guard !doc.id.isEmpty else { return false }
                guard let parentId = doc.parentId else { return true }
                return validFolderIds.contains(parentId)
            }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }

        var seen = Set<String>()
        return candidates.filter { doc in
            if seen.contains(doc.id) {
                return false
            }
            seen.insert(doc.id)
            return true
        }
    }

    var filteredDocuments: [Document] {
        guard !fileSearchText.isEmpty else { return availableDocuments }
        return availableDocuments.filter { doc in
            doc.name.localizedCaseInsensitiveContains(fileSearchText)
        }
    }

    var filesByParentMap: [String?: [Document]] {
        Dictionary(grouping: filteredDocuments, by: { $0.parentId })
    }

    var folderChildrenMap: [String: [Document]] {
        var map: [String: [Document]] = [:]
        for folder in allFolders {
            guard let parentId = folder.parentId, validFolderIds.contains(parentId) else { continue }
            map[parentId, default: []].append(folder)
        }
        for key in map.keys {
            map[key]?.sort { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        }
        return map
    }

    var rootFolders: [Document] {
        let inbox = allFolders.filter { $0.parentId == nil && $0.name == "Inbox" }
        let otherRoots = allFolders
            .filter { folder in
                folder.parentId == nil && folder.name != "Inbox"
            }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        return inbox + otherRoots
    }
}

private extension FilesNodeConfig {
    func removeFile(_ fileId: String) {
        selectedFileIds.removeAll { $0 == fileId }
        syncConfig()
    }

    func handleFileDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: String.self) { string, _ in
                guard let raw = string else { return }
                let docId = raw.hasPrefix("doc:") ? String(raw.dropFirst(4)) : raw
                Task { @MainActor in
                    guard let doc = self.documentStore.collections.first(where: { $0.id == docId }),
                          doc.docType == .file else { return }
                    if !self.selectedFileIds.contains(docId) {
                        self.selectedFileIds.append(docId)
                        self.syncConfig()
                    }
                }
            }
        }
        return true
    }

    func showFilePickerSheet() {
        fileSearchText = ""
        stagedPickerSelection = Set(selectedFileIds)
        expandedFolderIds = Set(rootFolders.map(\.id))
        showFilePicker = true
    }

    func togglePickerSelection(_ id: String) {
        if stagedPickerSelection.contains(id) {
            stagedPickerSelection.remove(id)
        } else {
            stagedPickerSelection.insert(id)
        }
    }

    func syncConfig() {
        if node.config == nil {
            node.config = [:]
        }
        node.config?["file_ids"] = .array(selectedFileIds.map { .string($0) })
    }

    func loadInitialState() {
        if let configValue = node.config?["file_ids"],
           case .array(let ids) = configValue {
            selectedFileIds = ids.compactMap {
                if case .string(let id) = $0 {
                    return id.hasPrefix("doc:") ? String(id.dropFirst(4)) : id
                }
                return nil
            }
        }
    }
}
