import SwiftUI

extension ChatInspector {
    var searchBarView: some View {
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
                        Task { @MainActor in
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
                .help("Clear the search")
            }
        }
        .padding(8)
        .background(Color(.controlBackgroundColor))
    }

    var searchResultsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(isSearching ? "Searching..." : "\(searchResults.count) results")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add All") {
                    for doc in searchResults {
                        selectedDocuments = ChatDocumentScope.attaching([doc.id], to: selectedDocuments)
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
                                    selectedDocuments = ChatDocumentScope.attaching([doc.id], to: selectedDocuments)
                                } label: {
                                    Image(systemName: "plus.circle")
                                        .foregroundColor(.accentColor)
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel("Add document to chat")
                                .help("Add this document to the chat scope")
                            }
                        }
                        // #4386: full-width row target, not the label's width.
                        .inspectorListRowTarget()
                        .onTapGesture {
                            if !selectedDocuments.contains(doc.id) {
                                selectedDocuments = ChatDocumentScope.attaching([doc.id], to: selectedDocuments)
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
    }
}
