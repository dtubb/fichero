import SwiftUI

// MARK: - FolderSectionView

/// Recursive folder-tree row for the file picker.
/// Extracted as a dedicated View struct so SwiftUI can structurally diff each
/// level without AnyView type-erasure defeating the diffing engine.
struct FolderSectionView: View {
    let folder: Document
    let depth: Int
    let ancestry: Set<String>
    let filesByParentMap: [String?: [Document]]
    let folderChildrenMap: [String: [Document]]
    @Binding var expandedFolderIds: Set<String>
    let stagedPickerSelection: Set<String>
    let onToggle: (String) -> Void

    var body: some View {
        if ancestry.contains(folder.id) {
            EmptyView()
        } else {
            let nextAncestry = ancestry.union([folder.id])
            DisclosureGroup(
                isExpanded: Binding(
                    get: { expandedFolderIds.contains(folder.id) },
                    set: { isExpanded in
                        if isExpanded {
                            expandedFolderIds.insert(folder.id)
                        } else {
                            expandedFolderIds.remove(folder.id)
                        }
                    }
                )
            ) {
                if let directFiles = filesByParentMap[folder.id], !directFiles.isEmpty {
                    ForEach(directFiles, id: \.id) { doc in
                        FilePickerRowView(
                            doc: doc,
                            depth: depth + 1,
                            isSelected: stagedPickerSelection.contains(doc.id),
                            onToggle: onToggle
                        )
                    }
                }

                if let children = folderChildrenMap[folder.id] {
                    ForEach(children, id: \.id) { child in
                        FolderSectionView(
                            folder: child,
                            depth: depth + 1,
                            ancestry: nextAncestry,
                            filesByParentMap: filesByParentMap,
                            folderChildrenMap: folderChildrenMap,
                            expandedFolderIds: $expandedFolderIds,
                            stagedPickerSelection: stagedPickerSelection,
                            onToggle: onToggle
                        )
                    }
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: folder.name == "Inbox" ? "tray.fill" : "folder")
                        .foregroundStyle(.secondary)
                    Text(folder.name)
                        .lineLimit(1)
                        .foregroundStyle(.primary)
                    Spacer()
                }
                .padding(.vertical, 4)
                .padding(.leading, 4)
                .padding(.trailing, 6)
            }
            .disclosureGroupStyle(.automatic)
        }
    }
}

// MARK: - FilePickerRowView

/// Single selectable file row for the file picker.
/// Extracted to give FolderSectionView a concrete (non-AnyView) child type.
struct FilePickerRowView: View {
    let doc: Document
    let depth: Int
    let isSelected: Bool
    let onToggle: (String) -> Void

    var body: some View {
        Button {
            onToggle(doc.id)
        } label: {
            HStack(spacing: 6) {
                Image(
                    systemName: isSelected
                        ? "checkmark.circle.fill"
                        : "circle"
                )
                .foregroundStyle(
                    isSelected
                        ? Color.accentColor
                        : Color.secondary
                )
                Image(systemName: doc.fileType?.icon ?? "doc")
                    .foregroundStyle(.secondary)
                Text(doc.name)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.vertical, 4)
            .padding(.leading, 6)
            .padding(.trailing, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(isSelected
                        ? Color.accentColor.opacity(0.12)
                        : Color.clear)
        )
    }
}
