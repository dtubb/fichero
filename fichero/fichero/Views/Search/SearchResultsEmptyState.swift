import SwiftUI

struct SearchResultsEmptyState: View {
    let currentQuery: String
    let isSearching: Bool
    let isReindexing: Bool
    let indexedCount: Int?
    let onReindex: (() -> Void)?
    let suggestions: [String]
    let onSuggestionTap: ((String) -> Void)?
    let recentSearches: [String]
    let onRecentSearchTap: ((String) -> Void)?
    let keywordCloud: [KeywordCloudEntryDTO]
    let onKeywordTap: ((String) -> Void)?

    var body: some View {
        VStack(spacing: 12) {
            if isSearching {
                ProgressView()
                Text("Searching…")
                    .font(.headline)
                    .foregroundStyle(.secondary)
            } else if isReindexing {
                ProgressView()
                Text("Indexing library…")
                    .font(.headline)
                    .foregroundStyle(.secondary)
                if let indexedCount, indexedCount > 0 {
                    Text("\(indexedCount) document\(indexedCount == 1 ? "" : "s") indexed so far")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                Text("""
                This runs in the background; you can keep using
                the rest of the app. Search will return results
                once indexing completes.
                """)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            } else if trimmedQuery.isEmpty {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                Text("Search Documents")
                    .font(.headline)
                if let indexedCount, indexedCount == 0, let onReindex {
                    Text("This library has no search index yet.\nIndex it once to enable search.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button(action: onReindex) {
                        Label("Index Library", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Text(
                        "Type a query in the toolbar (⌘F) to search across\n"
                        + "all transcribed documents in this library."
                    )
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    if let indexedCount, indexedCount > 0 {
                        Text("\(indexedCount) document\(indexedCount == 1 ? "" : "s") indexed")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                    if !keywordCloud.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Browse by keyword")
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                            // Count range computed ONCE for the whole cloud, not
                            // re-scanned per pill (#3870).
                            let cloudSizing = KeywordCloudSizing(cloud: keywordCloud)
                            FlowLayout(spacing: 4) {
                                ForEach(keywordCloud) { entry in
                                    Button {
                                        onKeywordTap?(entry.name)
                                    } label: {
                                        Text(entry.name)
                                            .font(.system(
                                                size: cloudSizing.fontSize(for: entry)
                                            ))
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 4)
                                            .background(Capsule().fill(Color.accentColor.opacity(0.10)))
                                            .overlay(Capsule().stroke(Color.accentColor.opacity(0.20), lineWidth: 0.5))
                                            .foregroundStyle(.primary)
                                    }
                                    .buttonStyle(.plain)
                                    .help("\(entry.count) document\(entry.count == 1 ? "" : "s")")
                                }
                            }
                        }
                        .frame(maxWidth: 480)
                        .padding(.top, 12)
                    }

                    if !recentSearches.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Recent")
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                            FlowLayout(spacing: 6) {
                                ForEach(recentSearches, id: \.self) { recent in
                                    Button {
                                        onRecentSearchTap?(recent)
                                    } label: {
                                        HStack(spacing: 4) {
                                            Image(systemName: "clock")
                                                .imageScale(.small)
                                            Text(recent)
                                        }
                                        .font(.caption)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 4)
                                        .background(
                                            Capsule().fill(Color.secondary.opacity(0.10))
                                        )
                                        .foregroundStyle(.primary)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                        .frame(maxWidth: 360)
                        .padding(.top, 8)
                    }
                }
            } else {
                Image(systemName: "doc.text.magnifyingglass")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                Text("No Matches")
                    .font(.headline)
                Text("Nothing matched “\(trimmedQuery)”.\nTry a shorter query or different terms.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                if !suggestions.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Did you mean…")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                        FlowLayout(spacing: 6) {
                            ForEach(suggestions, id: \.self) { suggestion in
                                Button {
                                    onSuggestionTap?(suggestion)
                                } label: {
                                    Text(suggestion)
                                        .font(.caption)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 4)
                                        .background(
                                            Capsule().fill(Color.accentColor.opacity(0.12))
                                        )
                                        .overlay(
                                            Capsule().stroke(Color.accentColor.opacity(0.25), lineWidth: 0.5)
                                        )
                                        .foregroundStyle(Color.accentColor)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .frame(maxWidth: 360)
                    .padding(.top, 8)
                }
                if let onReindex {
                    Button(action: onReindex) {
                        Label("Re-index Library", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .padding(.top, 4)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var trimmedQuery: String {
        currentQuery.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
