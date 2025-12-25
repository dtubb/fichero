import SwiftUI
import UniformTypeIdentifiers
import AppKit
import Combine

/// A reusable sidebar item row component
struct SidebarItemRow: View {
    let item: SidebarItem
    let section: SidebarSection  // Add section parameter
    @Binding var expandedItems: Set<String>
    @Binding var renamingItemId: String?
    @Binding var creatingFolderInlineId: String?
    @Binding var showingNewFolderDialog: Bool
    @Binding var newFolderParentId: String?
    @Binding var newFolderSection: SidebarSection?
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var documentService: DocumentService
    @EnvironmentObject var searchService: SavedSearchService
    @EnvironmentObject var conversationService: ConversationService
    @EnvironmentObject var workflowService: WorkflowService
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?
    
    // Drag and drop state
    @State private var isDragging = false
    @State private var isDropTargeted = false
    
    // Rename state
    @State private var renameError: String? = nil
    
    // Environment objects for caching
    @EnvironmentObject var cacheModel: CacheModel

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    var body: some View {
        Group {
            if let children = item.children, !children.isEmpty {
                DisclosureGroup(isExpanded: isExpanded) {
                    ForEach(children) { child in
                        SidebarItemRow(
                            item: child,
                            section: section,  // Pass same section to children
                            expandedItems: $expandedItems,
                            renamingItemId: $renamingItemId,
                            creatingFolderInlineId: $creatingFolderInlineId,
                            showingNewFolderDialog: $showingNewFolderDialog,
                            newFolderParentId: $newFolderParentId,
                            newFolderSection: $newFolderSection,
                            viewMode: $viewMode,
                            selectedItem: $selectedItem
                        )
                        .tag(child)
                    }
                } label: {
                    itemLabel
                }
                .onDrop(of: [.fileURL], isTargeted: $isDropTargeted) { providers -> Bool in
                    handleDrop(providers: providers)
                }
            } else {
                itemLabel
                    .onDrop(of: [.fileURL], isTargeted: $isDropTargeted) { providers -> Bool in
                        handleDrop(providers: providers)
                    }
            }
        }
        .overlay(
            // Visual indicator for drop targeting - section-specific feedback
            Group {
                if isDropTargeted {
                    switch section {
                    case .library:
                        // Grey highlight for library (adding to collection)
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.gray.opacity(0.6), lineWidth: 2)
                            .background(Color.gray.opacity(0.2))
                            .cornerRadius(4)
                            .overlay(
                                cacheModel.cachedSystemImage(named: "folder.badge.plus", color: .gray)
                                    .font(.system(size: 12))
                                    .padding(4),
                                alignment: .trailing
                            )
                    case .searches:
                        // Blue highlight for searches (searching within)
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.blue.opacity(0.6), lineWidth: 2)
                            .background(Color.blue.opacity(0.1))
                            .cornerRadius(4)
                            .overlay(
                                cacheModel.cachedSystemImage(named: "magnifyingglass", color: .blue)
                                    .font(.system(size: 12))
                                    .padding(4),
                                alignment: .trailing
                            )
                    case .chat:
                        // Green highlight for chat (adding to chat)
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.green.opacity(0.6), lineWidth: 2)
                            .background(Color.green.opacity(0.1))
                            .cornerRadius(4)
                            .overlay(
                                cacheModel.cachedSystemImage(named: "bubble.left.and.bubble.right", color: .green)
                                    .font(.system(size: 12))
                                    .padding(4),
                                alignment: .trailing
                            )
                    case .workflows:
                        // Purple highlight for workflows (adding to workflow canvas)
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.purple.opacity(0.6), lineWidth: 2)
                            .background(Color.purple.opacity(0.1))
                            .cornerRadius(4)
                            .overlay(
                                cacheModel.cachedSystemImage(named: "arrow.triangle.branch", color: .purple)
                                    .font(.system(size: 12))
                                    .padding(4),
                                alignment: .trailing
                            )
                    }
                }
            }
        )
    }

    private var itemLabel: some View {
        HStack {
            if renamingItemId == item.id {
                // Show inline rename field
                InlineRenameField(
                    currentName: item.name,
                    placeholder: "Enter new name",
                    onCommit: { newName in
                        try await handleRename(newName: newName)
                        renamingItemId = nil
                    },
                    onCancel: {
                        renamingItemId = nil
                    }
                )
                .transition(.opacity.combined(with: .scale))
            } else if creatingFolderInlineId == item.id {
                // Show inline folder creation field
                InlineFolderCreation(
                    section: section,
                    parentId: item.id,
                    onCommit: { folderName in
                        try await createNewFolder(name: folderName)
                        creatingFolderInlineId = nil
                    },
                    onCancel: {
                        creatingFolderInlineId = nil
                    }
                )
                .transition(.opacity.combined(with: .scale))
            } else {
                // Show normal label
                Label {
                    Text(item.name)
                        .lineLimit(1)
                } icon: {
                    cacheModel.cachedSystemImage(named: item.icon, color: iconColor)
                }

                Spacer()

                // Show progress indicator if enabled and progress is available
                if item.showProgress, let progress = item.progress {
                    ProgressView(value: progress, total: 1.0)
                        .progressViewStyle(LinearProgressViewStyle())
                        .frame(width: 40)
                        .scaleEffect(CGSize(width: 0.7, height: 0.7))
                }
            }
        }
        .opacity(isDragging ? 0.5 : 1.0)
        .background(isDropTargeted ? Color.accentColor.opacity(0.1) : Color.clear)
        .cornerRadius(4)
        .onDrag {
            // Only allow dragging for documents and folders
            if case .document(let document) = item.itemType {
                // Create item provider with document ID
                let provider = NSItemProvider(object: document.id as NSString)
                return provider
            }
            return NSItemProvider()
        }
        .contextMenu {
            switch item.itemType {
            case .document(let document):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let duplicatedDoc = try await documentService.duplicateDocument(document.id)
                            print("Document duplicated: \(duplicatedDoc.name)")
                            
                            // Show success alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Document Duplicated"
                                alert.informativeText = "\"\(duplicatedDoc.name)\" was successfully duplicated."
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }
                        } catch {
                            print("Error duplicating document: \(error)")
                            
                            // Show error alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Error Duplicating Document"
                                alert.informativeText = "Failed to duplicate document: \(error.localizedDescription)"
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("New Folder...") {
                    newFolderParentId = document.id
                    newFolderSection = .library
                    creatingFolderInlineId = document.id
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await documentService.deleteDocument(document.id)
                            print("Document deleted: \(document.name)")
                            
                            // Show success alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Document Deleted"
                                alert.informativeText = "\"\(document.name)\" was successfully deleted."
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }

                            // The reactive architecture will handle UI updates automatically
                        } catch {
                            print("Error deleting document: \(error)")
                            
                            // Show error alert
                            if let window = NSApp.keyWindow {
                                let alert = NSAlert()
                                alert.messageText = "Error Deleting Document"
                                alert.informativeText = "Failed to delete document: \(error.localizedDescription)"
                                alert.addButton(withTitle: "OK")
                                alert.beginSheetModal(for: window, completionHandler: nil)
                            }
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .savedSearch(let search):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let duplicatedSearch = try await searchService.duplicateSavedSearch(search.id)
                            print("Saved search duplicated: \(duplicatedSearch.query)")
                        } catch {
                            print("Error duplicating saved search: \(error)")
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("New Folder...") {
                    // For searches, we need to determine the appropriate parent
                    // Since searches might not have a traditional hierarchy, we'll use nil for now
                    newFolderParentId = nil
                    newFolderSection = .searches
                    creatingFolderInlineId = search.id
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await searchService.deleteSavedSearch(search.id)
                            print("Saved search deleted: \(search.name)")
                        } catch {
                            print("Error deleting saved search: \(error)")
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .conversation(let conversation):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let result = try await conversationService.duplicateConversation(conversation.id)
                            print("Conversation duplicated: \(result.title)")
                        } catch {
                            print("Error duplicating conversation: \(error)")
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("New Folder...") {
                    newFolderParentId = conversation.id
                    newFolderSection = .chat
                    creatingFolderInlineId = conversation.id
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await conversationService.deleteConversation(conversation.id)
                            print("Conversation deleted: \(conversation.title)")
                        } catch {
                            print("Error deleting conversation: \(error)")
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .workflow(let workflow):
                Button("Rename...") {
                    startRename()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Duplicate") {
                    Task {
                        do {
                            let duplicatedWorkflow = try await workflowService.duplicateWorkflow(workflow.id)
                            print("Workflow duplicated: \(duplicatedWorkflow.name)")
                        } catch {
                            print("Error duplicating workflow: \(error)")
                        }
                    }
                }
                .keyboardShortcut("d", modifiers: [.command, .shift])

                Divider()

                Button("Import...") {
                    // Placeholder for import workflow
                    print("Import workflow")
                }

                Button("Export...") {
                    // Placeholder for export workflow
                    print("Export workflow: \(item.name)")
                }

                Divider()

                Button("New Folder...") {
                    newFolderParentId = workflow.id
                    newFolderSection = .workflows
                    creatingFolderInlineId = workflow.id
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Divider()

                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await workflowService.deleteWorkflow(workflow.id)
                            print("Workflow deleted: \(workflow.name)")
                        } catch {
                            print("Error deleting workflow: \(error)")
                        }
                    }
                }
                .keyboardShortcut(.delete, modifiers: [])

            case .sectionHeader:
                // No context menu for section headers
                EmptyView()
            }
        }
    }

    private var iconColor: Color {
        switch item.section {
        case .library:
            return .accentColor
        case .searches:
            return .orange
        case .chat:
            return .green
        case .workflows:
            return .purple
        }
    }

    private func startRename() {
        renamingItemId = item.id
    }

    private func handleRename(newName: String) async throws {
        switch item.itemType {
        case .document(let document):
            let renamedDoc = try await documentService.renameDocument(document.id, newName: newName)
            NSLog("[Sidebar] Document renamed: %@ -> %@", document.name, renamedDoc.name)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Document Renamed"
                alert.informativeText = "\"\(document.name)\" was successfully renamed to \"\(renamedDoc.name)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .savedSearch(let search):
            let renamedSearch = try await searchService.renameSavedSearch(search.id, newName: newName)
            NSLog("[Sidebar] Search renamed: %@ -> %@", search.name, renamedSearch.query)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Search Renamed"
                alert.informativeText = "\"\(search.name)\" was successfully renamed to \"\(renamedSearch.query)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .conversation(let conversation):
            let renamedConv = try await conversationService.renameConversation(conversation.id, newTitle: newName)
            NSLog("[Sidebar] Conversation renamed: %@ -> %@", conversation.title, renamedConv.title)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Conversation Renamed"
                alert.informativeText = "\"\(conversation.title)\" was successfully renamed to \"\(renamedConv.title)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .workflow(let workflow):
            let renamedWorkflow = try await workflowService.renameWorkflow(workflow.id, newName: newName)
            NSLog("[Sidebar] Workflow renamed: %@ -> %@", workflow.name, renamedWorkflow.name)
            
            // Show success alert
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = "Workflow Renamed"
                alert.informativeText = "\"\(workflow.name)\" was successfully renamed to \"\(renamedWorkflow.name)\"."
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: window, completionHandler: nil)
            }

        case .sectionHeader:
            // Cannot rename section headers
            break
        }
    }

    private func createNewFolder(name: String) async throws {
        guard let section = newFolderSection else {
            throw NSError(domain: "com.fichero.sidebar",
                         code: 1,
                         userInfo: [NSLocalizedDescriptionKey: "No section specified for folder creation"])
        }

        // Create the folder using the appropriate service based on section
        let newFolder: Document
        switch section {
        case .library:
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        case .searches:
            // For searches, we'll create a folder in the searches section
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        case .chat:
            // For chat, we'll create a folder in the conversations section
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        case .workflows:
            // For workflows, we'll create a folder in the workflows section
            newFolder = try await documentService.createFolder(name: name, parentId: newFolderParentId)
        }

        // Show success alert
        if let window = NSApp.keyWindow {
            let alert = NSAlert()
            alert.messageText = "Folder Created"
            alert.informativeText = "\"\\(newFolder.name)\" was successfully created."
            alert.addButton(withTitle: "OK")
            alert.beginSheetModal(for: window, completionHandler: nil)
        }
    }

    /// Handle drop operation on this item
    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        var handled = false

        for provider in providers {
            // Handle file URLs (from Finder)
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { (urlData, error) in
                    DispatchQueue.main.async {
                        if let urlData = urlData as? Data,
                           let url = URL(dataRepresentation: urlData, relativeTo: nil) {
                            handleDroppedFile(url: url)
                            handled = true
                        }
                    }
                }
            }
            // Handle document IDs (from sidebar drag)
            else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { (data, error) in
                    DispatchQueue.main.async {
                        if let data = data as? Data,
                           let documentId = String(data: data, encoding: .utf8) {
                            handleDroppedDocument(documentId: documentId)
                            handled = true
                        }
                    }
                }
            }
        }

        return handled
    }

    /// Handle a file dropped from Finder
    private func handleDroppedFile(url: URL) {
        guard case .document(let targetDocument) = item.itemType else {
            NSLog("[Sidebar] Cannot drop file on non-document item")
            return
        }

        // Check if target is a collection or folder (can contain items)
        if targetDocument.docType == .collection || targetDocument.docType == .folder {
            NSLog("[Sidebar] File dropped on \(targetDocument.name): \(url.path)")
            
            // Defer the import operation to avoid layout recursion
            DispatchQueue.main.async {
                Task {
                    do {
                        let importedDoc = try await documentStore.importFile(at: url, parentId: targetDocument.id)
                        NSLog("[Sidebar] Successfully imported file: \(importedDoc.name)")
                        
                        // Show success alert
                        if let window = NSApp.keyWindow {
                            let alert = NSAlert()
                            alert.messageText = "File Imported"
                            alert.informativeText = "\"\(importedDoc.name)\" was successfully imported into \"\(targetDocument.name)\"."
                            alert.addButton(withTitle: "OK")
                            alert.beginSheetModal(for: window, completionHandler: nil)
                        }
                    } catch {
                        NSLog("[Sidebar] Error importing file: \(error)")
                        
                        // Show error alert
                        if let window = NSApp.keyWindow {
                            let alert = NSAlert()
                            alert.messageText = "Import Failed"
                            alert.informativeText = "Failed to import file: \(error.localizedDescription)"
                            alert.addButton(withTitle: "OK")
                            alert.beginSheetModal(for: window, completionHandler: nil)
                        }
                    }
                }
            }
        } else {
            NSLog("[Sidebar] Cannot drop file on document \(targetDocument.name) - not a container")
        }
    }

    /// Handle a document dropped from sidebar (reorganization)
    private func handleDroppedDocument(documentId: String) {
        guard case .document(let targetDocument) = item.itemType else {
            NSLog("[Sidebar] Cannot drop document on non-document item")
            return
        }

        // Prevent dropping on itself
        if documentId == targetDocument.id {
            NSLog("[Sidebar] Cannot drop document on itself")
            return
        }

        // Check if target is a collection or folder (can contain items)
        if targetDocument.docType == .collection || targetDocument.docType == .folder {
            NSLog("[Sidebar] Document \(documentId) dropped on \(targetDocument.name)")
            
            Task {
                do {
                    let movedDoc = try await documentStore.moveDocument(documentId, toParent: targetDocument.id)
                    NSLog("[Sidebar] Successfully moved document: \(movedDoc.name)")
                    
                    // Show success alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "Document Moved"
                        alert.informativeText = "\"\(movedDoc.name)\" was successfully moved into \"\(targetDocument.name)\"."
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                } catch {
                    NSLog("[Sidebar] Error moving document: \(error)")
                    
                    // Show error alert
                    if let window = NSApp.keyWindow {
                        let alert = NSAlert()
                        alert.messageText = "Move Failed"
                        alert.informativeText = "Failed to move document: \(error.localizedDescription)"
                        alert.addButton(withTitle: "OK")
                        alert.beginSheetModal(for: window, completionHandler: nil)
                    }
                }
            }
        } else {
            NSLog("[Sidebar] Cannot drop document on \(targetDocument.name) - not a container")
        }
    }
}