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

    private var availableDocuments: [Document] {
        let candidates = documentStore.collections
            .filter { $0.docType != .folder }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }

        var seen = Set<String>()
        return candidates.filter { doc in
            guard !doc.id.isEmpty else { return false }
            if seen.contains(doc.id) {
                return false
            }
            seen.insert(doc.id)
            return true
        }
    }

    private var filteredDocuments: [Document] {
        guard !fileSearchText.isEmpty else { return availableDocuments }
        return availableDocuments.filter {
            $0.name.localizedCaseInsensitiveContains(fileSearchText)
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
                        ForEach(filteredDocuments, id: \.id) { doc in
                            Button {
                                togglePickerSelection(doc.id)
                            } label: {
                                HStack {
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
                                    Text(doc.name)
                                        .foregroundStyle(.primary)
                                        .lineLimit(1)
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 6)
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
