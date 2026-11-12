import Foundation

/// The margin mark of one line in the Content view (#6458, `source.editor.content-shows-its-tie-to-the-lines`), read from the
/// line's counting reading: a reading made per segment is anchored and shows nothing; one tied from a page read shows the link,
/// yellow when doubtful; a line with no counting reading shows the dash.
enum ContentTieMark: Equatable {
    case anchored
    case tied(percent: Int?, reader: String)
    case doubtful(percent: Int, reader: String)
    case empty

    /// A tie scoring below this is doubtful. The measured threshold row of its reader kind replaces it
    /// (`source.tie.thresholds-are-measured`).
    static let doubtfulBelow = 0.6

    init(counting reading: InspectorText.Reading?) {
        guard let reading else {
            self = .empty
            return
        }
        guard reading.derivedFromArtifactId != nil else {
            self = .anchored
            return
        }
        let reader = reading.producerModel ?? "page"
        guard let confidence = reading.machineConfidence else {
            self = .tied(percent: nil, reader: reader)
            return
        }
        let percent = Int((confidence * 100).rounded())
        self = confidence < Self.doubtfulBelow ? .doubtful(percent: percent, reader: reader) : .tied(percent: percent, reader: reader)
    }

    /// The SF Symbol; nil when the line shows nothing.
    var glyph: String? {
        switch self {
        case .anchored: nil
        case .tied, .doubtful: "link"
        case .empty: "minus"
        }
    }

    var isDoubtful: Bool {
        if case .doubtful = self { true } else { false }
    }

    /// The tooltip and accessibility words.
    var help: String {
        switch self {
        case .anchored: "read line by line"
        case let .tied(percent, reader): "tied from \(reader)'s page read" + (percent.map { " · \($0) %" } ?? "")
        case let .doubtful(percent, reader): "doubtful tie from \(reader)'s page read · \(percent) %"
        case .empty: "no reading counts for this line"
        }
    }
}

/// The Content view's head line for page-only text, with the two verbs of #6415.
struct ContentTieHeadLine: Equatable {
    let text = "page text, not tied to lines"
    let verbs = ["Tie Automatically", "Tie by Hand"]

    init?(hasLineMap: Bool) {
        guard !hasLineMap else { return nil }
    }
}
