import OSLog
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
    /// In-app drop receiver for sidebar items dragged onto the library
    /// header — reparents them to the library root (parentId = nil) so
    /// the user can lift items out of nested folders and then reorder
    /// them at root via native row drops. Added to satisfy #711's
    /// "let me drop on the library at the top" workflow.
    var onSidebarItemDrop: (([String]) -> Void)?
    var onTap: (() -> Void)?

    @State private var isDropTargeted = false
    @State private var isItemDropTargeted = false

    var body: some View {
        headerContent
            .padding(.vertical, 2)
            .contentShape(Rectangle())
            .background(
                RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                    .fill(
                        (isDropTargeted || isItemDropTargeted)
                            ? Color.accentColor.opacity(0.25)
                            : Color.clear
                    )
            )
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted) { providers in
            // #600: UTI-agnostic filter — see SidebarItemRow+DropHandlers
            // for the rationale (.mov NSItemProvider may omit public.fileURL
            // while still being URL-loadable).
            let fileProviders = providers.filter { $0.canLoadObject(ofClass: URL.self) }
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
        .dropDestination(for: SidebarDragID.self, action: { ids, _ in
            Logger(subsystem: "com.tubb.Fichero", category: "LibraryHeaderDrop")
                .debug("🎯 LibrarySectionHeader .dropDestination FIRED with \(ids.count) ids")
            guard let onSidebarItemDrop else { return false }
            onSidebarItemDrop(ids.map(\.id))
            return true
        }, isTargeted: { isItemDropTargeted = $0 })
        // Sidebar plan Step 10 (#584): VoiceOver label reads e.g.
        // "Global, library, 42 documents". Hint guides users toward the
        // Finder-drop behaviour that isn't obvious without visual cues.
        .accessibilityLabel(accessibilityLabel)
        .accessibilityHint("Drag files from Finder here to import into this library, or drop a sidebar item to move it to the library root.")
    }

    /// Display name for this library row. "Global" for the global library,
    /// the user's display name otherwise.
    private var libraryName: String {
        library.id == LibraryManager.globalLibraryId ? "Global" : library.displayName
    }

    /// Row content — extracted into a `@ViewBuilder` to keep the body
    /// expression small enough for SourceKit to type-check in bounded
    /// time. The combined HStack with three conditional branches used
    /// to trip the "compiler unable to type-check this expression in
    /// reasonable time" warning (2026-04-17 review).
    @ViewBuilder
    private var headerContent: some View {
        HStack(spacing: 6) {
            Image(systemName: "books.vertical")
                .foregroundStyle(isCurrentLibrary ? Color.accentColor : Color.primary)
                .font(.system(size: 13))
            Text(libraryName)
            Spacer()
            if itemCount > 0 {
                Text("\(itemCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .simultaneousGesture(TapGesture().onEnded { onTap?() })
    }

    private var accessibilityLabel: String {
        if itemCount > 0 {
            let plural = itemCount == 1 ? "document" : "documents"
            return "\(libraryName), library, \(itemCount) \(plural)"
        }
        return "\(libraryName), library"
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
