import OSLog
import SwiftUI

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "FilesNodeConfig")

/// Configuration view for files node
struct FilesNodeConfig: View {
    @Binding var node: WorkflowNode

    @EnvironmentObject var documentStore: DocumentStore

    @State private var selectedFileIds: [String] = []
    @State private var showFilePicker = false
    @State private var stagedPickerSelection: Set<String> = []
    @State private var fileSearchText = ""
    @State private var expandedFolderIds: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Selected Files")
                .font(.caption)
                .foregroundColor(.secondary)

            // List of selected files
            if selectedFileIds.isEmpty {
                dropZoneView
            } else {
                VStack(spacing: 4) {
                    ForEach(selectedFileIds, id: \.self) { fileId in
                        fileRow(fileId: fileId)
                    }

                    // Add more files via drop or picker.
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

    private var dropZoneView: some View {
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

    private var allFolders: [Document] {
        documentStore.collections
            .filter { $0.docType == .folder }
            .sorted { lhs, rhs in
                lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
    }

    private var validFolderIds: Set<String> {
        Set(allFolders.map(\.id))
    }

    private var availableDocuments: [Document] {
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

    private var folderChildrenMap: [String: [Document]] {
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

    private var filesByParentMap: [String?: [Document]] {
        let files = filteredDocuments
        return Dictionary(grouping: files, by: { $0.parentId })
    }

    private var rootFolders: [Document] {
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

    private var filteredDocuments: [Document] {
        guard !fileSearchText.isEmpty else { return availableDocuments }
        return availableDocuments.filter { doc in
            doc.name.localizedCaseInsensitiveContains(fileSearchText)
        }
    }

    @ViewBuilder
    private func fileRow(fileId: String) -> some View {
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

    private func removeFile(_ fileId: String) {
        selectedFileIds.removeAll { $0 == fileId }
        syncConfig()
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: String.self) { string, _ in
                guard let docId = string else { return }
                Task { @MainActor in
                    if !self.selectedFileIds.contains(docId) {
                        self.selectedFileIds.append(docId)
                        self.syncConfig()
                    }
                }
            }
        }
        return true
    }

    private func showFilePickerSheet() {
        fileSearchText = ""
        stagedPickerSelection = Set(selectedFileIds)
        expandedFolderIds = Set(rootFolders.map(\.id))
        showFilePicker = true
    }

    private var filePickerPanel: some View {
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
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(rootFolders, id: \.id) { folder in
                            folderSection(folder, depth: 0, ancestry: [])
                        }

                        if let rootFiles = filesByParentMap[nil], !rootFiles.isEmpty {
                            Text("Root")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .padding(.top, 6)
                                .padding(.horizontal, 6)

                            ForEach(rootFiles, id: \.id) { doc in
                                filePickerRow(doc: doc, depth: 1)
                            }
                        }
                    }
                    .padding(2)
                }
                .frame(minHeight: 160, maxHeight: 240)
                .background(Color(.textBackgroundColor))
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
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(6)
    }

    private func togglePickerSelection(_ id: String) {
        if stagedPickerSelection.contains(id) {
            stagedPickerSelection.remove(id)
        } else {
            stagedPickerSelection.insert(id)
        }
    }

    private func folderSection(_ folder: Document, depth: Int, ancestry: Set<String>) -> AnyView {
        // Guard against malformed cyclic folder graphs in persisted data.
        guard !ancestry.contains(folder.id) else {
            return AnyView(EmptyView())
        }

        let nextAncestry = ancestry.union([folder.id])
        return AnyView(
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
                    filePickerRow(doc: doc, depth: depth + 1)
                }
            }

            if let children = folderChildrenMap[folder.id] {
                ForEach(children, id: \.id) { child in
                    folderSection(child, depth: depth + 1, ancestry: nextAncestry)
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
            .padding(.leading, CGFloat(depth) * 14 + 4)
            .padding(.trailing, 6)
            }
            .disclosureGroupStyle(.automatic)
        )
    }

    @ViewBuilder
    private func filePickerRow(doc: Document, depth: Int) -> some View {
        Button {
            togglePickerSelection(doc.id)
        } label: {
            HStack(spacing: 6) {
                Image(
                    systemName: stagedPickerSelection.contains(doc.id)
                        ? "checkmark.circle.fill"
                        : "circle"
                )
                .foregroundStyle(
                    stagedPickerSelection.contains(doc.id)
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
            .padding(.leading, CGFloat(depth) * 14 + 6)
            .padding(.trailing, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(stagedPickerSelection.contains(doc.id)
                    ? Color.accentColor.opacity(0.12)
                    : Color.clear)
        )
    }

    private func syncConfig() {
        if node.config == nil {
            node.config = [:]
        }
        node.config?["file_ids"] = .array(selectedFileIds.map { .string($0) })
    }

    private func loadInitialState() {
        if let configValue = node.config?["file_ids"],
           case .array(let ids) = configValue {
            selectedFileIds = ids.compactMap {
                if case .string(let id) = $0 {
                    return id
                }
                return nil
            }
        }
    }
}
