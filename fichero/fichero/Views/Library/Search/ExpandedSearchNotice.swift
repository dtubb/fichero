import SwiftUI

/// The "Expanded Search Results" notice shown above library search results
/// (Daniel, 2026-08-31 — modelled on Mail's search banner).
///
/// ## Why it can say what it says
///
/// The engine's `/search` really does run a vector leg: `search_type`
/// `"semantic"` and `"hybrid"` embed the query and search the LanceDB
/// embeddings table, then blend that with the full-text leg
/// (`Database.search`, `fichero_server/db/__init__.py`). `"fulltext"` does
/// not — it is keyword matching only.
///
/// So the notice is NOT mounted whenever a search is active. It is mounted
/// only when the search RESPONSE reports a mode that includes the semantic
/// leg — `shouldPresent(searchType:)` below — which is the engine's own
/// account of what it ran, not the client's hope about what it asked for.
/// A full-text search, a failed search, or a library with no results never
/// shows it.
///
/// Dismissal is permanent by design (`search.expandedResultsNoticeDismissed`):
/// this is a one-time explanation, not a state indicator, so it must not come
/// back on the next query.
struct ExpandedSearchNotice: View {
    /// Persisted dismissal. Once true the notice never returns until the key
    /// is reset.
    @AppStorage(ExpandedSearchNotice.dismissedKey) private var dismissed = false

    /// The mode the engine reports it actually performed (`SearchResponse.searchType`).
    let searchType: String

    // nonisolated: read from non-@MainActor Swift Testing suites (#4201).
    nonisolated static let dismissedKey = "search.expandedResultsNoticeDismissed"

    nonisolated static let title = "Expanded Search Results"
    nonisolated static let message =
        "Fichero can look for results based on what you mean, not just the words you type."

    /// True only for the engine modes that include the embeddings leg.
    /// `"fulltext"` — and anything unrecognised — is keyword-only, so the
    /// claim would be false and the notice stays away.
    nonisolated static func shouldPresent(searchType: String) -> Bool {
        searchType == "semantic" || searchType == "hybrid"
    }

    var body: some View {
        if !dismissed, Self.shouldPresent(searchType: searchType) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 2) {
                    Text(Self.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text(Self.message)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 8)

                Button {
                    dismissed = true
                } label: {
                    Image(systemName: "xmark")
                        .imageScale(.small)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Stop showing this notice")
                .accessibilityLabel("Close")
                .accessibilityIdentifier("expandedSearchNotice.close")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.blue.opacity(0.12))
            )
            .padding(.horizontal, 12)
            .padding(.bottom, 6)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("expandedSearchNotice")
        }
    }
}

#Preview("Expanded search notice") {
    ExpandedSearchNotice(searchType: "hybrid")
        .frame(width: 520)
        .padding()
}
