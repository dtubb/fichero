import Foundation

struct StatsResponse: Codable {
    let documents: Int
    let artifacts: Int
    let embeddingStats: EmbeddingStats

    enum CodingKeys: String, CodingKey {
        case documents
        case artifacts
        case embeddingStats = "embedding_stats"
    }
}

struct EmbeddingStats: Codable {
    let indexedCount: Int
    let tableExists: Bool

    enum CodingKeys: String, CodingKey {
        case indexedCount = "indexed_count"
        case tableExists = "table_exists"
    }
}
