import FicheroAPIClient
import SwiftUI

/// Info tab content for DocumentInspector
struct DocumentInspectorInfoTab: View {
    let document: Document

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
    }
}
