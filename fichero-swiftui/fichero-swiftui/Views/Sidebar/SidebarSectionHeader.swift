import SwiftUI

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
        .dropDestination(for: URL.self) { urls, _ in
            onFileDrop?(urls) ?? false
        } isTargeted: { targeted in
            isDropTargeted = targeted
        }
    }
}
