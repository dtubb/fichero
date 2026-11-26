import Foundation

/// The rules of a found model's card in the Models window, apart from any view (`models.search.is-the-finder`,
/// `models.bookmark.kept-not-added`, `models.window.shows-what-a-recipe-can-reach`, #6588): which list it is in
/// and its one verb. The facts come from the engine's candidate; nothing here asks the network.
enum ModelCandidateRules {
    /// Where a candidate stands for this Mac, as the engine says (`CandidateAvailability`).
    enum Availability: String, Sendable {
        case ships, installed, download, elsewhere
        case notHere = "not_here"
    }

    /// What the rules need of one candidate.
    struct Facts: Equatable, Sendable {
        let availability: Availability
        let bookmarked: Bool
        /// The key the bookmark routes take; nil for a card a search did not find on Hugging Face.
        let bookmarkKey: String?
        let refused: String?
        /// A download under way.
        let downloading: Bool
        /// Its size in words as the engine says it ("1.2 GB", "size not stated").
        let size: String
    }

    /// The window's lists over the candidates.
    enum List: Equatable, Sendable {
        case usableNow, bookmarked, found
    }

    /// Whether a candidate can be used at once: on this Mac or shipped, and not refused.
    static func isUsableNow(_ facts: Facts) -> Bool {
        facts.refused == nil && (facts.availability == .ships || facts.availability == .installed)
    }

    /// The candidates a list holds, the engine's order kept.
    static func rows(_ list: List, in all: [Facts]) -> [Facts] {
        switch list {
        case .usableNow: all.filter(isUsableNow)
        case .bookmarked: all.filter(\.bookmarked)
        case .found: all.filter { $0.bookmarkKey != nil }
        }
    }

    /// A card's one verb: Remove Bookmark for a kept card, Download for one that can be downloaded, Bookmark for a found card
    /// that cannot be used now, nil where nothing is pressable (refused, already usable, or downloading).
    static func verb(_ facts: Facts) -> String? {
        if facts.downloading { return nil }
        if facts.bookmarked { return "Remove Bookmark" }
        if facts.refused != nil { return nil }
        if facts.availability == .download { return "Download" }
        if isUsableNow(facts) { return nil }
        return facts.bookmarkKey == nil ? nil : "Bookmark"
    }

    /// The Usable words of a card: "Now", "After download (2.1 GB)", or the engine's reason it cannot.
    static func usableWords(_ facts: Facts) -> String {
        if let refused = facts.refused { return refused }
        if isUsableNow(facts) { return "Now" }
        switch facts.availability {
        case .download: return "After download (\(facts.size))"
        case .elsewhere: return "Runs elsewhere"
        default: return "Not on this Mac"
        }
    }

    /// Whether a card's name matches the search field's text; an empty field matches every card.
    static func matches(_ name: String, _ text: String) -> Bool {
        let words = text.trimmingCharacters(in: .whitespaces)
        return words.isEmpty || name.localizedCaseInsensitiveContains(words)
    }
}
