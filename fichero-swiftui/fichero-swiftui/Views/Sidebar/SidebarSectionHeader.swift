import SwiftUI
import UniformTypeIdentifiers

// Note: The previous `SidebarSectionHeader` (a Label-styled header with a
// String-only drop target) was removed after a code review confirmed it had
// zero call sites — sub-section labels in the sidebar use plain `Text`
// instead (see `SidebarView+ViewComponents.unifiedDisclosureSection`). Kept
// this file focused on `LibrarySectionHeader` below, which IS used as the
// library-name row and now accepts Finder URL drops (#582).

// MARK: - Library Section Header

/// Section header specifically for library grouping across sidebar modes.
/// Displays the library name (or "Global" for the global library) with an item count.
/// Shows a checkmark indicator when this library is the current active library.
///
/// Accepts Finder file URL drops at library root — previously had no drop
/// destination, which meant Finder drops on the library-name row silently
/// did nothing (#582). `onFileDrop` callers pass a closure that imports
/// the URLs into the library root via `importService.importFiles(...,
/// parentId: nil)`.
///
/// Uses `.onDrop(of: [.fileURL])` (NSItemProvider API) rather than
/// `.dropDestination(for: URL.self)` (Transferable API) so Finder folder
/// drags preserve the folder URL instead of being flattened into the
/// folder's child files (#587).
struct LibrarySectionHeader: View {
    let library: LibraryManager.LibraryReference
    let itemCount: Int
    var isCurrentLibrary: Bool = false
    var onFileDrop: (([URL]) -> Bool)?

    @State private var isDropTargeted = false

    var body: some View {
        HStack(spacing: 4) {
            // Current library indicator (checkmark)
            if isCurrentLibrary {
                Image(systemName: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(Color.accentColor)
            }

            if library.id == LibraryManager.globalLibraryId {
                Text("Global")
            } else {
                Text(library.displayName)
            }

            Spacer()

            if itemCount > 0 {
                Text("\(itemCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                .fill(isDropTargeted ? Color.accentColor.opacity(0.25) : Color.clear)
        )
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted) { providers in
            let fileProviders = providers.filter {
                $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier)
            }
            guard !fileProviders.isEmpty, let onFileDrop else { return false }
            Task {
                var urls: [URL] = []
                for provider in fileProviders {
                    if let url = try? await Self.loadURL(from: provider) {
                        urls.append(url)
                    }
                }
                guard !urls.isEmpty else { return }
                _ = await MainActor.run { onFileDrop(urls) }
            }
            return true
        }
    }

    private static func loadURL(from provider: NSItemProvider) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let url {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(throwing: NSError(domain: "LibraryHeaderDrop", code: -1))
                }
            }
        }
    }
}
