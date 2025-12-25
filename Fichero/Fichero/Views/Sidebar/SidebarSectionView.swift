import SwiftUI
import UniformTypeIdentifiers
import AppKit

/// A virtualized sidebar section that handles expansion and item rendering
struct SidebarSectionView: View {
    let title: String
    let icon: String
    let items: [SidebarItem]
    let section: SidebarSection
    @Binding var isExpanded: Bool
    @Binding var expandedItems: Set<String>
    @Binding var renamingItemId: String?
    @Binding var creatingFolderInlineId: String?
    @Binding var showingNewFolderDialog: Bool
    @Binding var newFolderParentId: String?
    @Binding var newFolderSection: SidebarSection?
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?
    
    var onDrop: (([NSItemProvider]) -> Bool)?
    @Binding var isDropTargeted: Bool
    var showNewItemButton: Bool = false
    var newItemAction: (() -> Void)? = nil
    
    // Performance optimization: cache section header
    @State private var cachedHeader: AnyView?
    
    var body: some View {
        VStack(spacing: 0) {
            // Section header with disclosure triangle
            sectionHeader
                .onTapGesture {
                    withAnimation {
                        isExpanded.toggle()
                    }
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
            
            // Section content (only shown when expanded)
            if isExpanded {
                LazyVStack(spacing: 0) {
                    ForEach(items) { item in
                        SidebarItemRow(
                            item: item,
                            section: section,
                            expandedItems: $expandedItems,
                            renamingItemId: $renamingItemId,
                            creatingFolderInlineId: $creatingFolderInlineId,
                            showingNewFolderDialog: $showingNewFolderDialog,
                            newFolderParentId: $newFolderParentId,
                            newFolderSection: $newFolderSection,
                            viewMode: $viewMode,
                            selectedItem: $selectedItem
                        )
                        .id(item.id) // Important for ScrollViewReader
                        .contentShape(Rectangle())
                        .onTapGesture {
                            // Handle item selection
                            selectedItem = item
                        }
                        .background(
                            selectedItem?.id == item.id ? 
                                Color.accentColor.opacity(0.1) : 
                                Color.clear
                        )
                        .cornerRadius(4)
                    }
                    
                    // New item button (if enabled)
                    if showNewItemButton, let newItemAction = newItemAction {
                        Button(
                            action: newItemAction,
                            label: {
                                Label("New...", systemImage: "plus")
                                    .foregroundColor(.secondary)
                                    .padding(.leading, 28) // Match indentation
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        )
                        .buttonStyle(.plain)
                        .padding(.vertical, 4)
                    }
                }
                .transition(.opacity.combined(with: .scale))
            }
        }
        .background(Color(.sidebarBackgroundColor))
    }
    
    // Cached section header for better performance
    private var sectionHeader: some View {
        if let cachedHeader = cachedHeader {
            return cachedHeader
        }
        
        let header = HStack {
            Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .frame(width: 16)
            
            Image(systemName: icon)
                .foregroundColor(sectionColor)
                .frame(width: 16, height: 16)
            
            Text(title)
                .font(.headline)
                .foregroundColor(.primary)
            
            Spacer()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(Color(.sidebarBackgroundColor))
        .contentShape(Rectangle())
        
        // Cache the header view
        cachedHeader = AnyView(header)
        return header
    }
    
    private var sectionColor: Color {
        switch section {
        case .library: return .accentColor
        case .searches: return .orange
        case .chat: return .green
        case .workflows: return .purple
        }
    }
}

// Preview for SidebarSectionView
struct SidebarSectionView_Previews: PreviewProvider {
    static var previews: some View {
        SidebarSectionView(
            title: "Library",
            icon: "folder",
            items: [
                SidebarItem(id: "1", name: "Documents", icon: "doc", itemType: .sectionHeader, section: .library),
                SidebarItem(id: "2", name: "Projects", icon: "folder", itemType: .sectionHeader, section: .library)
            ],
            section: .library,
            isExpanded: .constant(true),
            expandedItems: .constant([]),
            renamingItemId: .constant(nil),
            creatingFolderInlineId: .constant(nil),
            showingNewFolderDialog: .constant(false),
            newFolderParentId: .constant(nil),
            newFolderSection: .constant(nil),
            viewMode: .constant(.library(nil)),
            selectedItem: .constant(nil),
            onDrop: nil,
            isDropTargeted: .constant(false),
            showNewItemButton: true,
            newItemAction: {}
        )
        .frame(width: 200)
        .background(Color(.sidebarBackgroundColor))
    }
}