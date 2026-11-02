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
        /// The page text the tie did not tie to a line, kept so nothing the page reader wrote is lost
        /// (`wide.nomodel.untied-remainder-kept`); absent from an older result.
        var remainder: [Remainder]?
    }

    struct Remainder: Decodable, Equatable {
        let segmentId: String?
        let text: String
        let why: String

        enum CodingKeys: String, CodingKey {
            case segmentId = "segment_id"
            case text, why
        }
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
