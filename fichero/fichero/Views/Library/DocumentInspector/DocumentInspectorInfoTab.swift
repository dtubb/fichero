import FicheroAPIClient
import SwiftUI

/// Info tab content for DocumentInspector
struct DocumentInspectorInfoTab: View {
    let document: Document

    @EnvironmentObject private var libraryManager: LibraryManager
    @EnvironmentObject private var windowState: WindowState
    @EnvironmentObject private var documentStore: DocumentStore
    @State private var isUpdatingExclude = false
    @State private var excludeFromProcessingOverride: Bool?

    var isExcludedFromProcessing: Bool {
        excludeFromProcessingOverride ?? document.excludeFromProcessing
    }

    var body: some View {
        VStack(alignment: .center, spacing: 0) {
            headerSection
                .padding(.bottom, 8)

            Form {
                Section("Status") {
                    LabeledContent("State") {
                        HStack(spacing: 6) {
                            StatusBadge(status: document.status)
                            if document.status == .processing {
                                ProgressView().scaleEffect(0.7)
                            }
                        }
                    }
                    LabeledContent("Created") {
                        Text(document.createdAt, style: .date)
                    }
                    LabeledContent("Modified") {
                        Text(document.updatedAt, style: .relative)
                    }
                }

                Section("Class") {
                    DocumentPrototypePicker(
                        documentId: document.id,
                        initialKey: document.prototypeKey
                    )
                }

                // Workspace curated items + per-item node class (#1570 Phase 1).
                // Only shown for workspace folders — folded into the existing
                // inspector Form as one more Section (conservative placement).
                if document.isWorkspace {
                    Section("Curated Items") {
                        WorkspaceCuratedItemsSection(folderId: document.id)
                    }
                }

                Section("File") {
                    LabeledContent("Kind") {
                        Text(document.docType.rawValue.capitalized)
                    }
                    if let fileType = document.fileType {
                        LabeledContent("Type") {
                            Text(fileType.rawValue.capitalized)
                        }
                    }
                    if let fileSize = document.metadata["File_Size"]?.value as? Int {
                        LabeledContent("Size") {
                            Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                        }
                    }
                }

                Section("Related Claims") {
                    RelatedClaimsPanel(documentId: document.id)
                }

                Section("Citations") {
                    CitationGraphPanel(documentId: document.id)
                }

                Section("Bibliography") {
                    DocumentBibliographyPanel(documentId: document.id)
                }

                Section("Workflow History") {
                    WorkflowProvenancePanel(documentId: document.id)
                }
            }
            .formStyle(.grouped)
        }
        .onChange(of: document.id) { _, _ in
            excludeFromProcessingOverride = nil
        }
    }

    @MainActor
    func toggleExcludeFromProcessing() async {
        guard let library = currentLibrary else { return }

        isUpdatingExclude = true
        defer { isUpdatingExclude = false }

        do {
            let refreshed = try await library.documentServiceGenerated.batchExclude(
                documentIds: [document.id],
                excluded: !isExcludedFromProcessing
            )
            for updated in refreshed {
                documentStore.refreshLocalContent(updated)
                if updated.id == document.id {
                    excludeFromProcessingOverride = updated.excludeFromProcessing
                }
            }
        } catch {
            documentStore.error = error
        }
    }

    private var currentLibrary: LibraryManager.LibraryReference? {
        if let libraryId = windowState.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            return library
        }
        return libraryManager.globalLibrary
    }
}
