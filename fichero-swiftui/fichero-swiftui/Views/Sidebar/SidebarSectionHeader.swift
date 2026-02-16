import SwiftUI

/// Section header for sidebar sections (Library, Searches, Chat, Workflows).
///
/// Displays a labeled header with an icon and optional drop target support for drag & drop operations.
/// Uses standard sidebar styling constants for consistent appearance.
///
/// - Parameters:
///   - title: The display title for the section
///   - icon: SF Symbol name for the section icon
///   - onDrop: Optional closure called when items are dropped on this header
struct SidebarSectionHeader: View {
    let title: String
    let icon: String
    let onDrop: (([String]) -> Bool)?

    @State private var isDropTargeted = false

    init(title: String, icon: String, onDrop: (([String]) -> Bool)? = nil) {
        self.title = title
        self.icon = icon
        self.onDrop = onDrop
    }

    var body: some View {
        Label(title, systemImage: icon)
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
            .padding(.vertical, SidebarConstants.sectionHeaderVerticalPadding)
            .padding(.horizontal, SidebarConstants.sectionHeaderHorizontalPadding)
            .background(
                RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                    .fill(
                        isDropTargeted
                            ? Color.accentColor.opacity(SidebarConstants.sectionDropTargetOpacity)
                            : Color.clear
                    )
            )
            .dropDestination(for: String.self) { droppedIDs, _ in
                onDrop?(droppedIDs) ?? false
            } isTargeted: { isTargeted in
                isDropTargeted = isTargeted
            }
    }
}

// MARK: - Library Section Header

/// Section header specifically for library grouping across sidebar modes.
/// Displays the library name (or "Global" for the global library) with an item count.
/// Shows a checkmark indicator when this library is the current active library.
struct LibrarySectionHeader: View {
    let library: LibraryManager.LibraryReference
    let itemCount: Int
    var isCurrentLibrary: Bool = false

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
    }
}
