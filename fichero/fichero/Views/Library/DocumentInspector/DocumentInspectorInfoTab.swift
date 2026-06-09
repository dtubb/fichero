import FicheroAPIClient
import SwiftUI

/// Info tab — two-step progressive disclosure: attribute name + summary, select to reveal detail / edit.
struct DocumentInspectorInfoTab: View {
    let document: Document

    @EnvironmentObject private var libraryManager: LibraryManager
    @EnvironmentObject private var windowState: WindowState
    @EnvironmentObject private var documentStore: DocumentStore
    @State var isUpdatingExclude = false
    @State var excludeFromProcessingOverride: Bool?
    @State private var selectedAttribute: InfoAttribute?

    var isExcludedFromProcessing: Bool {
        excludeFromProcessingOverride ?? document.excludeFromProcessing
    }

    var body: some View {
        VStack(alignment: .center, spacing: 0) {
            headerSection
                .padding(.bottom, 8)

            List(selection: $selectedAttribute) {
                Section("Status") {
                    InfoAttributeRow(
                        name: "State",
                        summary: document.status.rawValue.capitalized,
                        isSelected: selectedAttribute == .state
                    ) {
                        HStack(spacing: 6) {
                            StatusBadge(status: document.status)
                            if document.status == .processing {
                                ProgressView().scaleEffect(0.7)
                            }
                        }
                    }
                    .tag(InfoAttribute.state)

                    InfoAttributeRow(
                        name: "Created",
                        summary: document.createdAt.formatted(date: .abbreviated, time: .omitted),
                        isSelected: selectedAttribute == .created
                    ) {
                        Text(document.createdAt, format: .dateTime)
                            .foregroundStyle(.secondary)
                    }
                    .tag(InfoAttribute.created)

                    InfoAttributeRow(
                        name: "Modified",
                        summary: document.updatedAt.formatted(.relative(presentation: .named)),
                        isSelected: selectedAttribute == .modified
                    ) {
                        Text(document.updatedAt, format: .dateTime)
                            .foregroundStyle(.secondary)
                    }
                    .tag(InfoAttribute.modified)
                }

                Section("Class") {
                    InfoAttributeRow(
                        name: "Class",
                        summary: document.prototypeKey ?? "Default",
                        isSelected: selectedAttribute == .documentClass
                    ) {
                        DocumentPrototypePicker(
                            documentId: document.id,
                            initialKey: document.prototypeKey
                        )
                    }
                    .tag(InfoAttribute.documentClass)
                }

                // Workspace curated items + per-item node class (#1570 Phase 1).
                if document.isWorkspace {
                    Section("Curated Items") {
                        WorkspaceCuratedItemsSection(folderId: document.id)
                            .selectionDisabled(true)
                    }
                }

                Section("File") {
                    InfoAttributeRow(
                        name: "Kind",
                        summary: document.docType.rawValue.capitalized,
                        isSelected: selectedAttribute == .kind
                    ) {
                        Text(document.docType.rawValue.capitalized)
                            .foregroundStyle(.secondary)
                    }
                    .tag(InfoAttribute.kind)

                    if let fileType = document.fileType {
                        InfoAttributeRow(
                            name: "Type",
                            summary: fileType.rawValue.capitalized,
                            isSelected: selectedAttribute == .fileType
                        ) {
                            Text(fileType.rawValue.capitalized)
                                .foregroundStyle(.secondary)
                        }
                        .tag(InfoAttribute.fileType)
                    }

                    if let fileSize = document.metadata["File_Size"]?.value as? Int {
                        InfoAttributeRow(
                            name: "Size",
                            summary: ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file),
                            isSelected: selectedAttribute == .fileSize
                        ) {
                            Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                                .foregroundStyle(.secondary)
                        }
                        .tag(InfoAttribute.fileSize)
                    }
                }

                Section("Related Claims") {
                    RelatedClaimsPanel(documentId: document.id)
                        .selectionDisabled(true)
                }

                Section("Citations") {
                    CitationGraphPanel(documentId: document.id)
                        .selectionDisabled(true)
                }

                Section("Bibliography") {
                    DocumentBibliographyPanel(documentId: document.id)
                        .selectionDisabled(true)
                }

                Section("Workflow History") {
                    WorkflowProvenancePanel(documentId: document.id)
                        .selectionDisabled(true)
                }
            }
            .listStyle(.inset)
        }
        .onChange(of: document.id) { _, _ in
            excludeFromProcessingOverride = nil
            selectedAttribute = nil
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
        if let library = libraryManager.getLibrary(id: windowState.libraryId) {
            return library
        }
        return libraryManager.globalLibrary
    }
}

// MARK: - Supporting types

private enum InfoAttribute: Hashable {
    case state, created, modified, kind, fileType, fileSize, documentClass
}

private struct InfoAttributeRow<Detail: View>: View {
    let name: String
    let summary: String
    let isSelected: Bool
    private let detail: () -> Detail

    init(name: String, summary: String, isSelected: Bool, @ViewBuilder detail: @escaping () -> Detail) {
        self.name = name
        self.summary = summary
        self.isSelected = isSelected
        self.detail = detail
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isSelected ? 6 : 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(name)
                    .fontWeight(.medium)
                Spacer()
                if !isSelected {
                    Text(summary)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            if isSelected {
                detail()
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(.vertical, 2)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }
}
