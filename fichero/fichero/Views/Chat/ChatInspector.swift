import OSLog
import SwiftUI
import UniformTypeIdentifiers

let chatInspectorLogger = Logger(subsystem: "app.fichero.fichero", category: "ChatInspector")

struct ChatInspector: View {
    @Binding var selectedDocuments: Set<String>
    let suggestedDocumentIDs: [String]
    var onAddSuggestedDocuments: (() -> Void)?

    @State var scopedDocuments: [Document] = []
    @State var listSelection: Set<String> = []
    @State var isLoading: Bool = false
    @State var isDropTargeted: Bool = false

    @State var searchText: String = ""
    @State var searchResults: [Document] = []
    @State var isSearching: Bool = false
    @State var showSearchResults: Bool = false

    @State var isExtracting: Bool = false
    @State var extractionResult: String?

    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var apiClient: APIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerView

            Divider()

            searchBarView

            Divider()

            if showSearchResults && !searchText.isEmpty {
                searchResultsView
            } else if selectedDocuments.isEmpty {
                emptyStateView
            } else if isLoading {
                loadingView
            } else {
                scopedDocumentsView
            }
        }
        .background(Color(.windowBackgroundColor))
        .onDrop(of: [.text, .plainText], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers: providers)
        }
        .overlay {
            if isDropTargeted {
                dropOverlay
            }
        }
        .onChange(of: selectedDocuments) { _, _ in
            Task { await loadScopedDocuments() }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadScopedDocuments()
        }
    }
}

extension ChatInspector {
    var suggestedDocumentSet: Set<String> {
        Set(suggestedDocumentIDs)
    }

    var mergedSuggestedDocuments: Set<String> {
        selectedDocuments.union(suggestedDocumentSet)
    }

    var pendingSuggestedDocumentCount: Int {
        suggestedDocumentSet.subtracting(selectedDocuments).count
    }

    var showsTouchScopeActions: Bool {
        #if canImport(UIKit)
        true
        #else
        false
        #endif
    }
}

#Preview("With Documents") {
    ChatInspector(
        selectedDocuments: .constant(["doc1", "doc2"]),
        suggestedDocumentIDs: ["doc3"]
    )
        .frame(width: 300, height: 500)
}

#Preview("Empty") {
    ChatInspector(
        selectedDocuments: .constant([]),
        suggestedDocumentIDs: ["doc1", "doc2"]
    )
        .frame(width: 300, height: 500)
}
