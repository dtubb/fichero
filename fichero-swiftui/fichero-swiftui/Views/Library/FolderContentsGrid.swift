import SwiftUI

/// Grid view showing the contents of a folder in the preview pane.
struct FolderContentsGrid: View {
    let folder: Document

    @EnvironmentObject private var libraryManager: LibraryManager

    @State private var children: [Document] = []
    @State private var isLoading = true

    private let columns = [
        GridItem(.adaptive(minimum: 100, maximum: 140), spacing: 12)
    ]

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading folder contents...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if children.isEmpty {
                ContentUnavailableView(
                    "Empty Folder",
                    systemImage: "folder",
                    description: Text("This folder has no documents")
                )
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(children) { doc in
                            FolderContentItem(document: doc)
                        }
                    }
                    .padding()
                }
            }
        }
        .task(id: folder.id) {
            await loadChildren()
        }
    }

    private func loadChildren() async {
        isLoading = true
        if let library = libraryManager.globalLibrary {
            children = await library.documentStore.children(of: folder.id)
        }
        isLoading = false
    }
}

/// A single item in the folder contents grid.
private struct FolderContentItem: View {
    let document: Document

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: document.docType == .folder
                  ? "folder.fill"
                  : (document.fileType?.icon ?? "doc"))
                .font(.system(size: 36))
                .foregroundStyle(document.docType == .folder ? Color.accentColor : .secondary)
                .frame(height: 44)

            Text(document.name)
                .font(.caption)
                .lineLimit(2)
                .multilineTextAlignment(.center)
        }
        .frame(width: 100, height: 90)
        .padding(8)
        .background(Color(.controlBackgroundColor).opacity(0.5))
        .cornerRadius(8)
    }
}
