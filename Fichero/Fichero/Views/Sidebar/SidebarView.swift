import SwiftUI
import UniformTypeIdentifiers
import AppKit
import Combine

/// Sidebar with Library, Searches, Chat, and Workflows sections
struct SidebarView: View {
    @StateObject private var viewModel: SidebarViewModel

    // Environment objects - injected from parent
    @EnvironmentObject private var documentStore: DocumentStore
    @EnvironmentObject private var searchService: SavedSearchService
    @EnvironmentObject private var conversationService: ConversationService
    @EnvironmentObject private var workflowService: WorkflowService
    @EnvironmentObject private var documentService: DocumentService
    @EnvironmentObject private var errorService: ErrorService
    @EnvironmentObject private var performanceService: PerformanceService
    @EnvironmentObject private var cacheModel: CacheModel

    // Callback when documents are dropped to create a new chat
    var onCreateChatWithDocuments: (([String]) -> Void)?

    // MARK: - Initialization
    init(
        viewMode: Binding<AppViewMode>,
        selectedItem: Binding<SidebarItem?>, 
        libraryItems: [SidebarItem],
        searchItems: [SidebarItem],
        chatItems: [SidebarItem],
        workflowItems: [SidebarItem],
        onCreateChatWithDocuments: (([String]) -> Void)? = nil
    ) {
        self._viewModel = StateObject(wrappedValue: SidebarViewModel(
            viewMode: viewMode,
            selectedItem: selectedItem,
            libraryItems: libraryItems,
            searchItems: searchItems,
            chatItems: chatItems,
            workflowItems: workflowItems
        ))
        self.onCreateChatWithDocuments = onCreateChatWithDocuments
    }

    var body: some View {
        // Inject dependencies from environment
        let viewModelWithDependencies = viewModel
        viewModelWithDependencies.injectDependencies(
            documentStore: documentStore,
            searchService: searchService,
            conversationService: conversationService,
            workflowService: workflowService,
            documentService: documentService,
            errorService: errorService,
            performanceService: performanceService
        )
        
        // Set the callback
        viewModelWithDependencies.onCreateChatWithDocuments = onCreateChatWithDocuments

        return ScrollView {
            ScrollViewReader { proxy in
                ZStack {
                    // Main content
                LazyVStack(spacing: 0) {
                    // LIBRARY section
                    SidebarSectionView(
                        title: "Library",
                        icon: "folder",
                        items: viewModel.libraryItems,
                        section: .library,
                        isExpanded: Binding(
                            get: { viewModel.isSectionExpanded(.library) },
                            set: { _ in viewModel.toggleSectionExpansion(.library) }
                        ),
                        expandedItems: Binding(
                            get: { viewModel.state.expandedItems },
                            set: { viewModel.state.expandedItems = $0 }
                        ),
                        renamingItemId: Binding(
                            get: { viewModel.state.renamingItemId },
                            set: { viewModel.state.renamingItemId = $0 }
                        ),
                        creatingFolderInlineId: Binding(
                            get: { viewModel.state.creatingFolderInlineId },
                            set: { viewModel.state.creatingFolderInlineId = $0 }
                        ),
                        showingNewFolderDialog: Binding(
                            get: { viewModel.state.showingNewFolderDialog },
                            set: { viewModel.state.showingNewFolderDialog = $0 }
                        ),
                        newFolderParentId: Binding(
                            get: { viewModel.state.newFolderParentId },
                            set: { viewModel.state.newFolderParentId = $0 }
                        ),
                        newFolderSection: Binding(
                            get: { viewModel.state.newFolderSection },
                            set: { viewModel.state.newFolderSection = $0 }
                        ),
                        viewMode: Binding(
                            get: { viewModel.viewMode },
                            set: { viewModel.viewMode = $0 }
                        ),
                        selectedItem: Binding(
                            get: { viewModel.selectedItem },
                            set: { viewModel.selectedItem = $0 }
                        ),
                        onDrop: { providers in
                            viewModel.handleLibrarySectionDrop(providers: providers)
                        },
                        isDropTargeted: Binding(
                            get: { viewModel.state.isLibraryDropTargeted },
                            set: { viewModel.state.isLibraryDropTargeted = $0 }
                        )
                    )
                    .onDrop(of: [.fileURL], isTargeted: Binding(
                        get: { viewModel.state.isLibraryDropTargeted },
                        set: { viewModel.state.isLibraryDropTargeted = $0 }
                    )) { providers -> Bool in
                        viewModel.handleLibrarySectionDrop(providers: providers)
                    }

                    // SEARCHES section
                    SidebarSectionView(
                        title: "Searches",
                        icon: "magnifyingglass",
                        items: viewModel.searchItems,
                        section: .searches,
                        isExpanded: Binding(
                            get: { viewModel.isSectionExpanded(.searches) },
                            set: { _ in viewModel.toggleSectionExpansion(.searches) }
                        ),
                        expandedItems: Binding(
                            get: { viewModel.state.expandedItems },
                            set: { viewModel.state.expandedItems = $0 }
                        ),
                        renamingItemId: Binding(
                            get: { viewModel.state.renamingItemId },
                            set: { viewModel.state.renamingItemId = $0 }
                        ),
                        creatingFolderInlineId: Binding(
                            get: { viewModel.state.creatingFolderInlineId },
                            set: { viewModel.state.creatingFolderInlineId = $0 }
                        ),
                        showingNewFolderDialog: Binding(
                            get: { viewModel.state.showingNewFolderDialog },
                            set: { viewModel.state.showingNewFolderDialog = $0 }
                        ),
                        newFolderParentId: Binding(
                            get: { viewModel.state.newFolderParentId },
                            set: { viewModel.state.newFolderParentId = $0 }
                        ),
                        newFolderSection: Binding(
                            get: { viewModel.state.newFolderSection },
                            set: { viewModel.state.newFolderSection = $0 }
                        ),
                        viewMode: Binding(
                            get: { viewModel.viewMode },
                            set: { viewModel.viewMode = $0 }
                        ),
                        selectedItem: Binding(
                            get: { viewModel.selectedItem },
                            set: { viewModel.selectedItem = $0 }
                        ),
                        onDrop: nil,
                        isDropTargeted: .constant(false),
                        showNewItemButton: true,
                        newItemAction: { viewModel.createNewSearch() }
                    )

                    // CHAT section - supports dropping documents to create new chat
                    SidebarSectionView(
                        title: "Chat",
                        icon: "bubble.left.and.bubble.right",
                        items: viewModel.chatItems,
                        section: .chat,
                        isExpanded: Binding(
                            get: { viewModel.isSectionExpanded(.chat) },
                            set: { _ in viewModel.toggleSectionExpansion(.chat) }
                        ),
                        expandedItems: Binding(
                            get: { viewModel.state.expandedItems },
                            set: { viewModel.state.expandedItems = $0 }
                        ),
                        renamingItemId: Binding(
                            get: { viewModel.state.renamingItemId },
                            set: { viewModel.state.renamingItemId = $0 }
                        ),
                        creatingFolderInlineId: Binding(
                            get: { viewModel.state.creatingFolderInlineId },
                            set: { viewModel.state.creatingFolderInlineId = $0 }
                        ),
                        showingNewFolderDialog: Binding(
                            get: { viewModel.state.showingNewFolderDialog },
                            set: { viewModel.state.showingNewFolderDialog = $0 }
                        ),
                        newFolderParentId: Binding(
                            get: { viewModel.state.newFolderParentId },
                            set: { viewModel.state.newFolderParentId = $0 }
                        ),
                        newFolderSection: Binding(
                            get: { viewModel.state.newFolderSection },
                            set: { viewModel.state.newFolderSection = $0 }
                        ),
                        viewMode: Binding(
                            get: { viewModel.viewMode },
                            set: { viewModel.viewMode = $0 }
                        ),
                        selectedItem: Binding(
                            get: { viewModel.selectedItem },
                            set: { viewModel.selectedItem = $0 }
                        ),
                        onDrop: { providers in
                            viewModel.handleChatDrop(providers: providers)
                        },
                        isDropTargeted: Binding(
                            get: { viewModel.state.isChatDropTargeted },
                            set: { viewModel.state.isChatDropTargeted = $0 }
                        ),
                        showNewItemButton: true,
                        newItemAction: { viewModel.createNewChat() }
                    )
                    .onDrop(of: [.text, .plainText], isTargeted: Binding(
                        get: { viewModel.state.isChatDropTargeted },
                        set: { viewModel.state.isChatDropTargeted = $0 }
                    )) { providers in
                        viewModel.handleChatDrop(providers: providers)
                    }

                    // WORKFLOWS section
                    SidebarSectionView(
                        title: "Workflows",
                        icon: "arrow.triangle.branch",
                        items: viewModel.workflowItems,
                        section: .workflows,
                        isExpanded: Binding(
                            get: { viewModel.isSectionExpanded(.workflows) },
                            set: { _ in viewModel.toggleSectionExpansion(.workflows) }
                        ),
                        expandedItems: Binding(
                            get: { viewModel.state.expandedItems },
                            set: { viewModel.state.expandedItems = $0 }
                        ),
                        renamingItemId: Binding(
                            get: { viewModel.state.renamingItemId },
                            set: { viewModel.state.renamingItemId = $0 }
                        ),
                        creatingFolderInlineId: Binding(
                            get: { viewModel.state.creatingFolderInlineId },
                            set: { viewModel.state.creatingFolderInlineId = $0 }
                        ),
                        showingNewFolderDialog: Binding(
                            get: { viewModel.state.showingNewFolderDialog },
                            set: { viewModel.state.showingNewFolderDialog = $0 }
                        ),
                        newFolderParentId: Binding(
                            get: { viewModel.state.newFolderParentId },
                            set: { viewModel.state.newFolderParentId = $0 }
                        ),
                        newFolderSection: Binding(
                            get: { viewModel.state.newFolderSection },
                            set: { viewModel.state.newFolderSection = $0 }
                        ),
                        viewMode: Binding(
                            get: { viewModel.viewMode },
                            set: { viewModel.viewMode = $0 }
                        ),
                        selectedItem: Binding(
                            get: { viewModel.selectedItem },
                            set: { viewModel.selectedItem = $0 }
                        ),
                        onDrop: nil,
                        isDropTargeted: .constant(false),
                        showNewItemButton: true,
                        newItemAction: { viewModel.createNewWorkflow() }
                    )
                }
                
                // Drag and drop overlay
                if viewModel.state.isProcessingDrop {
                    Color.black.opacity(0.1)
                        .ignoresSafeArea()
                        .overlay(
                            VStack(spacing: 8) {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                    .scaleEffect(1.5)
                                
                                Text("Processing Drop...")
                                    .font(.caption)
                                    .foregroundColor(.white)
                                
                                if viewModel.state.dropProgress > 0 {
                                    ProgressView(value: viewModel.state.dropProgress)
                                        .progressViewStyle(LinearProgressViewStyle(tint: .white))
                                        .frame(width: 150)
                                }
                                
                                if let errorMessage = viewModel.state.dropErrorMessage {
                                    Text(errorMessage)
                                        .font(.caption)
                                        .foregroundColor(.red)
                                        .multilineTextAlignment(.center)
                                        .padding(.top, 4)
                                }
                            }
                        )
                        .transition(.opacity)
                }
                }
                .background(
                    // Handle selection by detecting taps on items
                    Color.clear
                        .contentShape(Rectangle())
                        .onTapGesture {
                            // This ensures the scroll view can receive taps
                        }
                )
                .onChange(of: viewModel.selectedItem) { _, newItem in
                    viewModel.handleSelection(newItem)
                    // Scroll to selected item
                    if let newItem = newItem {
                        withAnimation {
                            proxy.scrollTo(newItem.id, anchor: .center)
                        }
                    }
                }
            }
        }
        .frame(minWidth: 200, maxWidth: .infinity)
        .background(Color(.sidebarBackgroundColor))
        .sheet(isPresented: Binding(
            get: { viewModel.state.showingNewFolderDialog },
            set: { viewModel.state.showingNewFolderDialog = $0 }
        )) {
            VStack(spacing: 16) {
                // Title
                Text("New Folder")
                    .font(.headline)

                // Text field
                TextField("Enter folder name", text: Binding(
                    get: { viewModel.state.newFolderName },
                    set: { viewModel.state.newFolderName = $0 }
                ))
                .textFieldStyle(.roundedBorder)
                .disableAutocorrection(true)

                // Error message
                if let errorMessage = viewModel.state.newFolderErrorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                // Buttons
                HStack {
                    Button("Cancel") {
                        viewModel.state.showingNewFolderDialog = false
                        viewModel.state.newFolderName = ""
                        viewModel.state.newFolderErrorMessage = nil
                    }
                    .keyboardShortcut(.cancelAction)

                    Spacer()

                    Button("Create") {
                        Task {
                            await viewModel.createNewFolderInline()
                        }
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(viewModel.state.newFolderName.isEmpty || viewModel.state.isCreatingFolder)
                    .overlay {
                        if viewModel.state.isCreatingFolder {
                            ProgressView()
                                .scaleEffect(0.7)
                        }
                    }
                }
            }
            .padding()
            .frame(width: 300)
        }
        .onAppear {
            // Start performance monitoring when sidebar appears
            viewModel.startPerformanceMonitoring()
        }
        .onDisappear {
            // Stop performance monitoring when sidebar disappears
            viewModel.stopPerformanceMonitoring()
        }
    }
}

#Preview {
    SidebarView(
        viewMode: .constant(.library(nil)),
        selectedItem: .constant(nil),
        libraryItems: [],
        searchItems: [],
        chatItems: [],
        workflowItems: []
    )
    .frame(width: 250, height: 500)
}