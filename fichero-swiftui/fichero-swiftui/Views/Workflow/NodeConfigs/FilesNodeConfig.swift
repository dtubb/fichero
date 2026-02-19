import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "FilesNodeConfig")

/// Configuration view for files node
struct FilesNodeConfig: View {
    @Binding var node: WorkflowNode
    
    @EnvironmentObject var documentStore: DocumentStore
    
    @State private var selectedFileIds: [String] = []
    
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
                    
                    // Add more files drop zone
                    dropZoneView
                }
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
                    Text("Drop files here or select from library")
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
    
    @ViewBuilder
    private func fileRow(fileId: String) -> some View {
        // Look up document name from current documents or collections
        let allDocs = documentStore.currentDocuments + documentStore.collections
        let docName = allDocs.first(where: { $0.id == fileId })?.name ?? "Document \(fileId.prefix(8))..."
        
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
        if node.config == nil {
            node.config = [:]
        }
        node.config?["file_ids"] = .array(selectedFileIds.map { .string($0) })
    }
    
    private func handleFileDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: String.self) { string, _ in
                guard let docId = string else { return }
                Task { @MainActor in
                    if !self.selectedFileIds.contains(docId) {
                        self.selectedFileIds.append(docId)
                        if self.node.config == nil {
                            self.node.config = [:]
                        }
                        self.node.config?["file_ids"] = .array(self.selectedFileIds.map { .string($0) })
                    }
                }
            }
        }
        return true
    }
    
    private func showFilePickerSheet() {
        // For now, users can drag files from the library browser
        // A picker sheet could be added in the future
        logger.debug("File picker sheet would open here")
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
