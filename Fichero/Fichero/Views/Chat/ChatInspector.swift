import SwiftUI
import UniformTypeIdentifiers
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ChatInspector")

/// Inspector panel for managing chat document scope
struct ChatInspector: View {
    @Binding var selectedDocuments: Set<String>

    @State private var scopedDocuments: [Document] = []  // Documents in scope with full info
    @State private var listSelection: Set<String> = []   // Selection within the list
    @State private var isLoading: Bool = false
    @State private var isDropTargeted: Bool = false

    // Search state
    @State private var searchText: String = ""
    @State private var searchResults: [Document] = []
    @State private var isSearching: Bool = false
    @State private var showSearchResults: Bool = false

    // Text extraction state
    @State private var isExtracting: Bool = false
    @State private var extractionResult: String?

    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var apiClient: APIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header with actions
            headerView

            Divider()

            // Search bar to find documents
            searchBarView

            Divider()

            // Main content: search results or scoped documents
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

// MARK: - View Components

extension ChatInspector {
    // MARK: - Header

    private var headerView: some View {
        HStack {
            Text("Chat Scope")
                .font(.headline)

            Spacer()

            if !selectedDocuments.isEmpty {
                // Select All button
                Button {
                    listSelection = selectedDocuments
                } label: {
                    Text("Select All")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .keyboardShortcut("a", modifiers: .command)

                // Remove selected button
                Button {
                    removeSelectedFromScope()
                } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .disabled(listSelection.isEmpty)
                .keyboardShortcut(.delete, modifiers: [])

                // Clear all button
                Button {
                    selectedDocuments.removeAll()
                    listSelection.removeAll()
                } label: {
                    Text("Clear")
                        .font(.caption)
                }
                .buttonStyle(.plain)
            }
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Search Bar

    private var searchBarView: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)

            TextField("Search documents to add...", text: $searchText)
                .textFieldStyle(.plain)
                .onSubmit {
                    Task { await performSearch() }
                }
                .onChange(of: searchText) { _, newValue in
                    if newValue.isEmpty {
                        showSearchResults = false
                        searchResults = []
                    } else {
                        showSearchResults = true
                        // Debounced search
                        Task {
                            try? await Task.sleep(nanoseconds: 300_000_000)
                            if searchText == newValue {
                                await performSearch()
                            }
                        }
                    }
                }

            if !searchText.isEmpty {
                Button {
                    searchText = ""
                    showSearchResults = false
                    searchResults = []
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(8)
        .background(Color(.controlBackgroundColor))
    }

    // MARK: - Search Results

    private var searchResultsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Results header
            HStack {
                Text(isSearching ? "Searching..." : "\(searchResults.count) results")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add All") {
                    for doc in searchResults {
                        selectedDocuments.insert(doc.id)
                    }
                    searchText = ""
                    showSearchResults = false
                }
                .font(.caption)
                .buttonStyle(.plain)
                .disabled(searchResults.isEmpty)
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color(.controlBackgroundColor).opacity(0.5))

            if isSearching {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if searchResults.isEmpty {
                VStack(spacing: 8) {
                    Text("No documents found")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(searchResults) { doc in
                        HStack {
                            Image(systemName: doc.fileType?.icon ?? "doc")
                                .foregroundColor(.secondary)
                            Text(doc.name)
                                .lineLimit(1)
                            Spacer()
                            if selectedDocuments.contains(doc.id) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                            } else {
                                Button {
                                    selectedDocuments.insert(doc.id)
                                } label: {
                                    Image(systemName: "plus.circle")
                                        .foregroundColor(.accentColor)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            if !selectedDocuments.contains(doc.id) {
                                selectedDocuments.insert(doc.id)
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    // MARK: - Scoped Documents View

    private var scopedDocumentsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Scope info bar
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)

                Text("\(selectedDocuments.count) in scope")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if !listSelection.isEmpty {
                    Text("• \(listSelection.count) selected")
                        .font(.caption)
                        .foregroundColor(.accentColor)
                }

                Spacer()
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color(.controlBackgroundColor).opacity(0.5))

            // Document list
            List(selection: $listSelection) {
                ForEach(scopedDocuments) { doc in
                    ScopedDocumentRow(document: doc)
                        .tag(doc.id)
                }
                .onDelete { indexSet in
                    let idsToRemove = indexSet.map { scopedDocuments[$0].id }
                    for id in idsToRemove {
                        selectedDocuments.remove(id)
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "plus.rectangle.on.folder")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No documents in scope")
                .font(.subheadline)
                .foregroundColor(.secondary)

            Text("Search above or drag documents from Library to focus your chat.")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            Divider()
                .padding(.vertical, 8)

            // Extract Text section
            VStack(spacing: 8) {
                Text("Document Maintenance")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isExtracting {
                    HStack {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Extracting text...")
                            .font(.caption)
                    }
                } else {
                    Button {
                        Task { await extractAllText() }
                    } label: {
                        Label("Extract Text from All Documents", systemImage: "doc.text.magnifyingglass")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }

                if let result = extractionResult {
                    Text(result)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Loading

    private var loadingView: some View {
        VStack {
            ProgressView()
            Text("Loading...")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Drop Overlay

    private var dropOverlay: some View {
        ZStack {
            Color.accentColor.opacity(0.15)
            VStack(spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .font(.title)
                    .foregroundColor(.accentColor)
                Text("Drop to add to scope")
                    .font(.subheadline)
                    .foregroundColor(.accentColor)
            }
        }
        .cornerRadius(8)
        .padding(4)
    }
}

// MARK: - Actions

extension ChatInspector {
    func removeSelectedFromScope() {
        for id in listSelection {
            selectedDocuments.remove(id)
        }
        listSelection.removeAll()
    }

    private func performSearch() async {
        guard !searchText.isEmpty else { return }

        isSearching = true

        do {
            // Search documents by name (simple filter for now)
            let allDocs: [Document] = try await apiClient.get("/documents", query: ["limit": "100"])
            let filtered = allDocs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) &&
                $0.docType == .file
            }
            await MainActor.run {
                searchResults = filtered
                isSearching = false
            }
        } catch {
            logger.error("Search error: \(error.localizedDescription)")
            await MainActor.run {
                searchResults = []
                isSearching = false
            }
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.text.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        Task { @MainActor in
                            selectedDocuments.insert(docId)
                            logger.info("Added document via drop: \(docId)")
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        Task { @MainActor in
                            selectedDocuments.insert(docId)
                            logger.info("Added document via drop: \(docId)")
                        }
                    }
                }
            }
        }
        return true
    }

    private func loadScopedDocuments() async {
        guard !selectedDocuments.isEmpty else {
            await MainActor.run { scopedDocuments = [] }
            return
        }

        isLoading = true
        var loadedDocs: [Document] = []

        for docId in selectedDocuments {
            do {
                let doc: Document = try await apiClient.get("/documents/\(docId)")
                loadedDocs.append(doc)
            } catch {
                logger.error("Failed to load doc \(docId): \(error.localizedDescription)")
            }
        }

        await MainActor.run {
            scopedDocuments = loadedDocs.sorted { $0.name < $1.name }
            isLoading = false
            listSelection = listSelection.intersection(selectedDocuments)
        }
    }

    func extractAllText() async {
        isExtracting = true
        extractionResult = nil

        do {
            let response = try await chatService.extractText(documentIds: nil, force: false)
            await MainActor.run {
                extractionResult = "Done: \(response.extracted) extracted, \(response.skipped) skipped"
                isExtracting = false
            }
        } catch {
            await MainActor.run {
                extractionResult = "Error: \(error.localizedDescription)"
                isExtracting = false
            }
        }
    }
}

// MARK: - Scoped Document Row

/// Row view for displaying a document in the chat scope list
struct ScopedDocumentRow: View {
    let document: Document

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: document.fileType?.icon ?? "doc")
                .foregroundColor(.secondary)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(document.name)
                    .font(.subheadline)
                    .lineLimit(1)

                if let fileType = document.fileType {
                    Text(fileType.rawValue.capitalized)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }
}

// MARK: - Preview

#Preview("With Documents") {
    ChatInspector(selectedDocuments: .constant(["doc1", "doc2"]))
        .frame(width: 300, height: 500)
}

#Preview("Empty") {
    ChatInspector(selectedDocuments: .constant([]))
        .frame(width: 300, height: 500)
}
