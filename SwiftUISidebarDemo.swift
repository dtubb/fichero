import SwiftUI
import UniformTypeIdentifiers

// MARK: - Data Model
struct SidebarItem: Identifiable, Codable, Hashable {
    var id = UUID()
    var name: String
    var isFolder: Bool
    var children: [SidebarItem] = []
    var parentId: UUID?

    var displayName: String {
        name.isEmpty ? (isFolder ? "Untitled Folder" : "Untitled Item") : name
    }

    init(name: String, isFolder: Bool = false, parentId: UUID? = nil) {
        self.name = name
        self.isFolder = isFolder
        self.parentId = parentId
    }
}

extension UTType {
    static var sidebarItem = UTType(exportedAs: "com.example.sidebaritem")
}

extension SidebarItem: Transferable {
    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .sidebarItem)
    }
}

// MARK: - Main Sidebar View
struct SwiftUISidebarDemo: View {
    @StateObject private var dataModel = SidebarDataModel()

    var body: some View {
        NavigationSplitView {
            SidebarView(dataModel: dataModel)
        } detail: {
            ContentView(dataModel: dataModel)
        }
        .environmentObject(dataModel)
    }
}

// MARK: - Sidebar View
struct SidebarView: View {
    @ObservedObject var dataModel: SidebarDataModel
    @State private var isAddingFolder = false
    @State private var newFolderName = ""

    var body: some View {
        NavigationStack {
            List {
                ForEach(dataModel.rootItems) { item in
                    SidebarItemRow(item: item, dataModel: dataModel)
                        .contextMenu {
                            ContextMenuView(item: item, dataModel: dataModel)
                        }
                }
                .onMove { fromOffsets, toOffset in
                    dataModel.moveItems(fromOffsets: fromOffsets, toOffset: toOffset, parentID: nil as UUID?)
                }
                .onDelete { indexSet in
                    dataModel.deleteItems(at: indexSet, parentID: nil as UUID?)
                }
            }
            .navigationTitle("Sidebar")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button("Add Folder") {
                        isAddingFolder = true
                    }
                }
            }
            .sheet(isPresented: $isAddingFolder) {
                AddFolderView(folderName: $newFolderName) { name in
                    dataModel.addFolder(name: name.isEmpty ? "New Folder" : name, parentID: nil as UUID?)
                    newFolderName = ""
                }
            }
        }
    }
}

// MARK: - Sidebar Item Row
struct SidebarItemRow: View {
    let item: SidebarItem
    @ObservedObject var dataModel: SidebarDataModel
    @State private var isRenaming = false
    @State private var renameText = ""
    @State private var isExpanded = false

    var body: some View {
        if item.isFolder {
            DisclosureGroup(isExpanded: $isExpanded, content: {
                ForEach(dataModel.getChildren(for: item.id)) { child in
                    SidebarItemRow(item: child, dataModel: dataModel)
                        .contextMenu {
                            ContextMenuView(item: child, dataModel: dataModel)
                        }
                }
                .onMove { fromOffsets, toOffset in
                    dataModel.moveItems(fromOffsets: fromOffsets, toOffset: toOffset, parentID: item.id)
                }
                .onDelete { indexSet in
                    dataModel.deleteItems(at: indexSet, parentID: item.id)
                }
            }, label: {
                HStack {
                    Image(systemName: "folder.fill")
                        .foregroundColor(.orange)
                    Text(item.displayName)
                }
                .draggable(item)
                .dropDestination(for: SidebarItem.self) { items, _ in
                    dataModel.moveItemsIntoFolder(items: items, folderID: item.id)
                    return true
                }
            })
        } else {
            HStack {
                Image(systemName: "doc.fill")
                    .foregroundColor(.blue)
                Text(item.displayName)
            }
            .draggable(item)
            .onTapGesture {
                dataModel.selectItem(item)
            }
            .contextMenu {
                ContextMenuView(item: item, dataModel: dataModel)
            }
        }
    }
}

// MARK: - Context Menu View
struct ContextMenuView: View {
    let item: SidebarItem
    @ObservedObject var dataModel: SidebarDataModel
    @State private var isRenaming = false
    @State private var renameText = ""
    @State private var isAddingSubfolder = false
    @State private var newSubfolderName = ""

    var body: some View {
        Group {
            Button(
                action: {
                    isRenaming = true
                    renameText = item.name
                },
                label: {
                    Label("Rename", systemImage: "pencil")
                }
            )

            if item.isFolder {
                Button(
                    action: {
                        isAddingSubfolder = true
                        newSubfolderName = ""
                    },
                    label: {
                        Label("Add Subfolder", systemImage: "folder.badge.plus")
                    }
                )
            }

            Button(
                action: {
                    dataModel.deleteItem(item)
                },
                label: {
                    Label("Delete", systemImage: "trash")
                }
            )
        }
        .sheet(isPresented: $isRenaming) {
            RenameItemView(currentName: $renameText) { newName in
                let finalName = newName.isEmpty ? (item.isFolder ? "Untitled Folder" : "Untitled Item") : newName
                dataModel.renameItem(item, to: finalName)
            }
        }
        .sheet(isPresented: $isAddingSubfolder) {
            AddFolderView(folderName: $newSubfolderName) { name in
                let folderName = name.isEmpty ? "New Folder" : name
                dataModel.addFolder(name: folderName, parentID: item.id)
                newSubfolderName = ""
            }
        }
    }
}

// MARK: - Add Folder View
struct AddFolderView: View {
    @Binding var folderName: String
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                TextField("Folder Name", text: $folderName)
                    .textFieldStyle(RoundedBorderTextFieldStyle())

                HStack {
                    Button("Cancel") {
                        dismiss()
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Button("Add") {
                        onSave(folderName)
                        dismiss()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(folderName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .padding()
            .navigationTitle("New Folder")
            .onSubmit {
                if !folderName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    onSave(folderName)
                    dismiss()
                }
            }
        }
    }
}

// MARK: - Rename Item View
struct RenameItemView: View {
    @Binding var currentName: String
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                TextField("Name", text: $currentName)
                    .textFieldStyle(RoundedBorderTextFieldStyle())

                HStack {
                    Button("Cancel") {
                        dismiss()
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Button("Rename") {
                        onSave(currentName)
                        dismiss()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(currentName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .padding()
            .navigationTitle("Rename")
            .onSubmit {
                if !currentName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    onSave(currentName)
                    dismiss()
                }
            }
        }
    }
}

// MARK: - Content View
struct ContentView: View {
    @ObservedObject var dataModel: SidebarDataModel

    var body: some View {
        VStack {
            if let selectedItem = dataModel.selectedItem {
                Text("Selected Item: \(selectedItem.displayName)")
                    .font(.title2)
                    .padding()

                Text(selectedItem.isFolder ? "This is a folder" : "This is a file")
                    .foregroundColor(.secondary)
            } else {
                Text("No item selected")
                    .font(.title2)
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

// MARK: - Data Model
class SidebarDataModel: ObservableObject {
    @Published var items: [SidebarItem] = [
        SidebarItem(name: "Documents", isFolder: true),
        SidebarItem(name: "Projects", isFolder: true),
        SidebarItem(name: "Notes.txt", isFolder: false),
        SidebarItem(name: "Settings.json", isFolder: false)
    ]

    @Published var selectedItem: SidebarItem?

    var rootItems: [SidebarItem] {
        items.filter { $0.parentId == nil }
    }

    func getChildren(for parentID: UUID) -> [SidebarItem] {
        items.filter { $0.parentId == parentID }
    }

    func addFolder(name: String, parentID: UUID?) {
        let newItem = SidebarItem(name: name, isFolder: true, parentId: parentID)
        items.append(newItem)
    }

    func addItem(name: String, parentID: UUID?) {
        let newItem = SidebarItem(name: name, isFolder: false, parentId: parentID)
        items.append(newItem)
    }

    func renameItem(_ item: SidebarItem, to newName: String) {
        if let index = items.firstIndex(where: { $0.id == item.id }) {
            items[index].name = newName
        }
    }

    func deleteItem(_ item: SidebarItem) {
        // Remove the item
        items.removeAll { $0.id == item.id }

        // Remove any children of this item
        items.removeAll { $0.parentId == item.id }
    }

    func deleteItems(at offsets: IndexSet, parentID: UUID?) {
        let filteredItems = items.filter { $0.parentId == parentID }
        let itemsToDelete = offsets.compactMap { index in
            if index < filteredItems.count {
                return filteredItems[index]
            }
            return nil
        }

        for item in itemsToDelete {
            deleteItem(item)
        }
    }

    func moveItems(fromOffsets: IndexSet, toOffset: Int, parentID: UUID?) {
        var filteredItems = items.filter { $0.parentId == parentID }

        // Keep track of the original items to update their positions
        filteredItems.move(fromOffsets: fromOffsets, toOffset: toOffset)

        // Update the original array with the new order
        // Remove the filtered items first
        items.removeAll { $0.parentId == parentID }
        // Add them back in the new order
        items.append(contentsOf: filteredItems)
    }

    func moveItemsIntoFolder(items: [SidebarItem], folderID: UUID) {
        for item in items {
            if let index = self.items.firstIndex(where: { $0.id == item.id }) {
                self.items[index].parentId = folderID
            }
        }
    }

    func selectItem(_ item: SidebarItem) {
        selectedItem = item
    }
}

// MARK: - Preview
#Preview {
    SwiftUISidebarDemo()
}
