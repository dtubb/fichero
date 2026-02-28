import SwiftUI

/// Complete filter UI panel for search view
struct SearchFiltersPanel: View {
    @Binding var queryText: String
    @Binding var isSmartSearch: Bool
    @Binding var searchType: String
    @Binding var sortBy: String
    @Binding var sortOrder: String
    @Binding var filters: SearchFilters

    let onSearch: () -> Void
    let onClear: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Search query
                VStack(alignment: .leading, spacing: 8) {
                    Text("Query")
                        .font(.headline)

                    TextField("Search documents...", text: $queryText)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit {
                            onSearch()
                        }

                    Toggle("Smart Search (AI)", isOn: $isSmartSearch)
                        .font(.caption)
                }

                // Search Type
                VStack(alignment: .leading, spacing: 8) {
                    Text("Search Type")
                        .font(.headline)

                    Picker("Search Type", selection: $searchType) {
                        Text("Hybrid").tag("hybrid")
                        Text("Semantic").tag("semantic")
                        Text("Full-Text").tag("fulltext")
                    }
                    .pickerStyle(.segmented)
                }

                Divider()

                // Sort Options
                VStack(alignment: .leading, spacing: 8) {
                    Text("Sort By")
                        .font(.headline)

                    Picker("Sort Field", selection: $sortBy) {
                        Text("Relevance").tag("relevance")
                        Text("Date").tag("date")
                        Text("Name").tag("name")
                    }
                    .pickerStyle(.menu)

                    Picker("Order", selection: $sortOrder) {
                        Text("Descending").tag("desc")
                        Text("Ascending").tag("asc")
                    }
                    .pickerStyle(.segmented)
                }

                Divider()

                // Document Type filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("Document Type")
                        .font(.headline)

                    ForEach(DocType.allCases, id: \.self) { type in
                        Toggle(type.rawValue.capitalized, isOn: binding(for: type))
                            .font(.subheadline)
                    }
                }

                Divider()

                // File Type filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("File Type")
                        .font(.headline)

                    ForEach(FileType.allCases, id: \.self) { type in
                        Toggle(type.rawValue.capitalized, isOn: binding(for: type))
                            .font(.subheadline)
                    }
                }

                Divider()

                // Status filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("Status")
                        .font(.headline)

                    ForEach(Status.allCases, id: \.self) { status in
                        Toggle(status.rawValue.capitalized, isOn: binding(for: status))
                            .font(.subheadline)
                    }
                }

                Divider()

                // Content filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("Content")
                        .font(.headline)

                    Picker("Has Content", selection: $filters.hasContent) {
                        Text("Any").tag(nil as Bool?)
                        Text("With Text").tag(true as Bool?)
                        Text("Without Text").tag(false as Bool?)
                    }
                    .pickerStyle(.segmented)
                }

                Spacer()

                // Actions
                HStack {
                    Button("Clear") {
                        onClear()
                    }

                    Spacer()

                    Button("Search") {
                        onSearch()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding()
        }
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Binding Helpers

    private func binding(for docType: DocType) -> Binding<Bool> {
        Binding(
            get: { filters.docTypes?.contains(docType) ?? false },
            set: { isOn in
                var types = filters.docTypes ?? []
                if isOn {
                    types.append(docType)
                } else {
                    types.removeAll { $0 == docType }
                }
                filters.docTypes = types.isEmpty ? nil : types
            }
        )
    }

    private func binding(for fileType: FileType) -> Binding<Bool> {
        Binding(
            get: { filters.fileTypes?.contains(fileType) ?? false },
            set: { isOn in
                var types = filters.fileTypes ?? []
                if isOn {
                    types.append(fileType)
                } else {
                    types.removeAll { $0 == fileType }
                }
                filters.fileTypes = types.isEmpty ? nil : types
            }
        )
    }

    private func binding(for status: Status) -> Binding<Bool> {
        Binding(
            get: { filters.statuses?.contains(status) ?? false },
            set: { isOn in
                var statuses = filters.statuses ?? []
                if isOn {
                    statuses.append(status)
                } else {
                    statuses.removeAll { $0 == status }
                }
                filters.statuses = statuses.isEmpty ? nil : statuses
            }
        )
    }
}
