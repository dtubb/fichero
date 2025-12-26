import SwiftUI
import AppKit

/// Simple sidebar item row component
struct SidebarItemRow: View {
    let item: SidebarItem
    let section: SidebarSection
    @Binding var viewMode: AppViewMode
    @Binding var selectedItem: SidebarItem?
    
    @EnvironmentObject var cacheModel: CacheModel
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var documentService: DocumentService
    @EnvironmentObject var searchService: SavedSearchService
    @EnvironmentObject var conversationService: ConversationService
    @EnvironmentObject var workflowService: WorkflowService
    
    var body: some View {
        HStack {
            // Icon
            cacheModel.cachedSystemImage(named: item.icon, color: iconColor)
                .frame(width: 16, height: 16)
            
            // Name
            Text(item.name)
                .lineLimit(1)
                .font(.system(size: 13))
            
            Spacer()
            
            // Progress indicator if needed
            if item.showProgress, let progress = item.progress {
                ProgressView(value: progress, total: 1.0)
                    .progressViewStyle(LinearProgressViewStyle())
                    .frame(width: 40)
                    .scaleEffect(CGSize(width: 0.7, height: 0.7))
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .contentShape(Rectangle())
        .background(selectedItem?.id == item.id ? Color.accentColor.opacity(0.1) : Color.clear)
        .cornerRadius(4)
        .onTapGesture {
            selectedItem = item
        }
        .contextMenu {
            itemContextMenu
        }
        .onDrag {
            // Support dragging for documents and conversations
            switch item.itemType {
            case .document(let doc):
                return NSItemProvider(object: doc.id as NSString)
            case .conversation(let conv):
                return NSItemProvider(object: conv.id as NSString)
            default:
                return NSItemProvider()
            }
        }
    }
    
    @ViewBuilder
    private var itemContextMenu: some View {
        switch item.itemType {
        case .document(let document):
            documentContextMenu(for: document)
        case .savedSearch(let search):
            searchContextMenu(for: search)
        case .conversation(let conversation):
            conversationContextMenu(for: conversation)
        case .workflow(let workflow):
            workflowContextMenu(for: workflow)
        case .sectionHeader:
            EmptyView()
        }
    }
    
    @ViewBuilder
    private func documentContextMenu(for document: Document) -> some View {
        Group {
            Button("Rename...") {
                Task {
                    do {
                        let newName = "Renamed \(document.name)"
                        let renamedDoc = try await documentService.renameDocument(document.id, newName: newName)
                        print("Document renamed: \(renamedDoc.name)")
                    } catch {
                        print("Error renaming: \(error)")
                    }
                }
            }
            
            Button("Delete", role: .destructive) {
                Task {
                    do {
                        try await documentService.deleteDocument(document.id)
                        print("Document deleted")
                    } catch {
                        print("Error deleting: \(error)")
                    }
                }
            }
        }
    }
    
    @ViewBuilder  
    private func searchContextMenu(for search: SavedSearch) -> some View {
        Group {
            Button("Rename...") {
                Task {
                    do {
                        let newName = "Renamed \(search.name)"
                        let renamedSearch = try await searchService.renameSavedSearch(search.id, newName: newName)
                        print("Search renamed: \(renamedSearch.query)")
                    } catch {
                        print("Error renaming: \(error)")
                    }
                }
            }
            
            Button("Delete", role: .destructive) {
                Task {
                    do {
                        try await searchService.deleteSavedSearch(search.id)
                        print("Search deleted")
                    } catch {
                        print("Error deleting: \(error)")
                    }
                }
            }
        }
    }
    
    @ViewBuilder
    private func conversationContextMenu(for conversation: Conversation) -> some View {
        Group {
            Button("Rename...") {
                Task {
                    do {
                        let newTitle = "Renamed \(conversation.title)"
                        let renamedConv = try await conversationService.renameConversation(conversation.id, newTitle: newTitle)
                        print("Conversation renamed: \(renamedConv.title)")
                    } catch {
                        print("Error renaming: \(error)")
                    }
                }
            }
            
            Button("Delete", role: .destructive) {
                Task {
                    do {
                        try await conversationService.deleteConversation(conversation.id)
                        print("Conversation deleted")
                    } catch {
                        print("Error deleting: \(error)")
                    }
                }
            }
        }
    }
    
    @ViewBuilder
    private func workflowContextMenu(for workflow: WorkflowSidebarItem) -> some View {
        Group {
            Button("Rename...") {
                Task {
                    do {
                        let newName = "Renamed \(workflow.name)"
                        let renamedWorkflow = try await workflowService.renameWorkflow(workflow.id, newName: newName)
                        print("Workflow renamed: \(renamedWorkflow.name)")
                    } catch {
                        print("Error renaming: \(error)")
                    }
                }
            }
            
            Button("Delete", role: .destructive) {
                Task {
                    do {
                        try await workflowService.deleteWorkflow(workflow.id)
                        print("Workflow deleted")
                    } catch {
                        print("Error deleting: \(error)")
                    }
                }
            }
        }
    }
    
    private var iconColor: Color {
        switch item.section {
        case .library: return .accentColor
        case .searches: return .orange  
        case .chat: return .green
        case .workflows: return .purple
        }
    }
}

// Preview
