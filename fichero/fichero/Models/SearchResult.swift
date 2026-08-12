import FicheroAPIClient
import Foundation

/// Search result from semantic search
struct SearchResult: Identifiable, Codable {
    var id: String { documentId }
    let documentId: String
    let score: Double
    let contentPreview: String?
    let metadata: [String: AnyCodable]
    let highlights: [String]?  // Highlighted text snippets
    let transcriptExcerpts: [Components.Schemas.SearchExcerpt]

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case score
        case contentPreview = "content_preview"
        case metadata
        case highlights
        case transcriptExcerpts = "transcript_excerpts"
    }

    init(
        documentId: String,
        score: Double,
        contentPreview: String?,
        metadata: [String: AnyCodable],
        highlights: [String]?,
        transcriptExcerpts: [Components.Schemas.SearchExcerpt] = []
    ) {
        self.documentId = documentId
        self.score = score
        self.contentPreview = contentPreview
        self.metadata = metadata
        self.highlights = highlights
        self.transcriptExcerpts = transcriptExcerpts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        documentId = try container.decode(String.self, forKey: .documentId)
        score = try container.decode(Double.self, forKey: .score)
        contentPreview = try container.decodeIfPresent(String.self, forKey: .contentPreview)
        metadata = try container.decode([String: AnyCodable].self, forKey: .metadata)
        highlights = try container.decodeIfPresent([String].self, forKey: .highlights)
        transcriptExcerpts = try container.decodeIfPresent(
            [Components.Schemas.SearchExcerpt].self,
            forKey: .transcriptExcerpts
        ) ?? []
    }
}

/// What a library row needs from a search hit (#11, Daniel 2026-08-11:
/// "it'd be good to show in the list of the library the relevant text in
/// search … and the results relevance on the right hand side"): the matched
/// text — the answer to "why did 'Colombia' get us this image?" — and its
/// score. The full excerpt (char span + anchor) stays on SearchResult for
/// the coming sentence-level highlight provenance.
struct TransientSearchRowHit: Equatable, Sendable {
    let excerpt: String?
    let score: Double
}

extension SearchResult {
    /// The best row-sized explanation of the match: a transcript excerpt
    /// (verbatim, span-anchored) first, then an FTS highlight, then the
    /// generic content preview.
    var rowHit: TransientSearchRowHit {
        TransientSearchRowHit(
            excerpt: transcriptExcerpts.first?.text ?? highlights?.first ?? contentPreview,
            score: score
        )
    }
}
