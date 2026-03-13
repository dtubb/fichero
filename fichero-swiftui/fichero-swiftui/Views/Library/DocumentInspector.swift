import SwiftUI

/// Tab selection for document inspector
enum InspectorTab: String, CaseIterable, Identifiable {
    case content = "Content"
    case info = "Info"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .content: return "doc.text"
        case .info: return "info.circle"
        }
    }
}

/// Inspector panel showing document metadata and details
struct DocumentInspector: View {
    let document: Document?

    @SceneStorage("DocumentInspector.selectedTab") private var selectedTab: InspectorTab = .content

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 220, maxWidth: .infinity)
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        VStack(spacing: 0) {
            // Xcode-style icon-only tab bar
            HStack(spacing: 2) {
                ForEach(InspectorTab.allCases) { tab in
                    Button {
                        selectedTab = tab
                    } label: {
                        Image(systemName: tab.icon)
                            .font(.system(size: 16, weight: .regular))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 7)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(selectedTab == tab
                                  ? Color.accentColor.opacity(0.15)
                                  : Color.clear)
                    )
                    .foregroundStyle(selectedTab == tab ? Color.accentColor : Color.secondary)
                    .help(tab.rawValue)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)

            Divider()

            // Tab Content
            switch selectedTab {
            case .content:
                DocumentInspectorContentTab(document: doc)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .info:
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        DocumentInspectorInfoTab(document: doc)
                        if !doc.metadata.isEmpty || doc.path != nil {
                            DocumentInspectorMetadataTab(document: doc)
                        }
                        DocumentInspectorArtifactsTab(documentId: doc.id)
                        Spacer()
                    }
                    .padding()
                }
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "sidebar.right")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Selection")
                .font(.headline)

            Text("Select a document to view details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Helpers

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

// MARK: - Preview

#Preview("Empty") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    DocumentInspector(document: nil)
        .environmentObject(library.artifactService)
        .frame(width: 280, height: 400)
}

#Preview("With Document") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    let mockDocument = Document(
        id: UUID().uuidString,
        parentId: nil,
        docType: .file,
        fileType: .pdf,
        name: "Sample Document.pdf",
        path: nil,
        sequence: nil,
        bbox: nil,
        status: .completed,
        metadata: [:],
        pageContent: nil,
        createdAt: Date(),
        updatedAt: Date()
    )

    DocumentInspector(document: mockDocument)
        .environmentObject(library.artifactService)
        .frame(width: 280, height: 400)
}
