import SwiftUI

/// Bookmark surface (#2755): bookmark the current document, list saved
/// bookmarks, and open one (resolve → its target document). All persistence
/// goes through the typed `BookmarkService`.
struct BookmarksView: View {
    /// The document offered for bookmarking (the row the sheet was opened from).
    let document: Document
    /// Opens a resolved target document in the host window.
    var onOpen: (Document) -> Void

    @Environment(BookmarkService.self) private var bookmarkService
    @Environment(DocumentService.self) private var documentService
    @Environment(\.dismiss) private var dismiss

    @State private var name: String = ""
    @State private var isWorking = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Bookmarks")
                .font(.headline)

            HStack(spacing: 8) {
                TextField("Bookmark name", text: $name)
                    .textFieldStyle(.roundedBorder)
                Button("Add", action: addBookmark)
                    .keyboardShortcut(.defaultAction)
                    .disabled(isWorking || trimmedName.isEmpty)
            }
            .help("Bookmark “\(DocumentTitle.displayName(for: document))”")

            Divider()

            if bookmarkService.bookmarks.isEmpty {
                Text("No bookmarks yet.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 16)
            } else {
                List(bookmarkService.bookmarks) { bookmark in
                    Button { open(bookmark) } label: {
                        Label(bookmark.name, systemImage: "bookmark")
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
                .frame(minHeight: 160)
            }

            if let error = bookmarkService.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            HStack {
                Spacer()
                Button("Done") { dismiss() }
            }
        }
        .padding(16)
        .frame(width: 360)
        .task {
            name = document.name
            await bookmarkService.loadBookmarks()
        }
    }

    private var trimmedName: String {
        name.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func addBookmark() {
        let bookmarkName = trimmedName
        guard !bookmarkName.isEmpty else { return }
        isWorking = true
        Task {
            _ = await bookmarkService.createBookmark(targetId: document.id, name: bookmarkName)
            isWorking = false
        }
    }

    private func open(_ bookmark: BookmarkItem) {
        isWorking = true
        Task {
            defer { isWorking = false }
            guard let targetId = await bookmarkService.resolveBookmark(id: bookmark.id),
                  let target = try? await documentService.getDocument(targetId) else { return }
            dismiss()
            onOpen(target)
        }
    }
}
