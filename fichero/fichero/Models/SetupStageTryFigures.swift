import Foundation

/// Read's tie figures from a try (`wide.nomodel.tie-figures-on-his-pages`).
struct SetupStageTie: Decodable, Equatable {
    struct Counts: Decodable, Equatable {
        let tied: Int?
        let doubtful: Int?
        let untied: Int?
        let drafts: Int?
    }

    struct PageFigures: Decodable, Equatable {
        let tied: Int
        let doubtful: Int
        let untied: Int
        let draft: Bool
    }

    let counts: Counts?
    let pages: [String: PageFigures]?
}

/// Find Lines' counts on the photograph and on the clarified copy (`wide.faded.line-counts-before-and-after`).
struct SetupStageLineCounts: Decodable, Equatable {
    struct Both: Decodable, Equatable {
        let photograph: Int
        let clarified: Int
    }

    let pages: [String: Both]?
    let notClarified: [String]?

    enum CodingKeys: String, CodingKey {
        case pages
        case notClarified = "not_clarified"
    }
}
