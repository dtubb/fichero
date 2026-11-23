@testable import Fichero
import Foundation
import Testing

/// `models.search.is-the-finder`, `models.bookmark.kept-not-added`, `models.window.shows-what-a-recipe-can-reach` (#6588):
/// which list a found card is in, its one verb and its Usable words.
struct ModelCandidateRulesTests {
    private func facts(_ availability: ModelCandidateRules.Availability, bookmarked: Bool = false, key: String? = "acme/reader",
                       refused: String? = nil, downloading: Bool = false) -> ModelCandidateRules.Facts {
        .init(availability: availability, bookmarked: bookmarked, bookmarkKey: key, refused: refused,
              downloading: downloading, size: "2.1 GB")
    }

    @Test("usable now is what ships or is installed and is not refused")
    func usableNow() {
        let all = [facts(.ships), facts(.installed), facts(.download), facts(.installed, refused: "no model for this script")]
        #expect(ModelCandidateRules.rows(.usableNow, in: all).count == 2)
    }

    @Test("the bookmarked list holds the kept cards; found holds the cards a search found")
    func lists() {
        let all = [facts(.download, bookmarked: true), facts(.download), facts(.ships, key: nil)]
        #expect(ModelCandidateRules.rows(.bookmarked, in: all).count == 1)
        #expect(ModelCandidateRules.rows(.found, in: all).count == 2)
    }

    @Test("a card has one verb: Remove Bookmark, Download, Bookmark, or none")
    func verbs() {
        #expect(ModelCandidateRules.verb(facts(.download, bookmarked: true)) == "Remove Bookmark")
        #expect(ModelCandidateRules.verb(facts(.download)) == "Download")
        #expect(ModelCandidateRules.verb(facts(.elsewhere)) == "Bookmark")
        #expect(ModelCandidateRules.verb(facts(.installed)) == nil)
        #expect(ModelCandidateRules.verb(facts(.download, refused: "no")) == nil)
        #expect(ModelCandidateRules.verb(facts(.download, downloading: true)) == nil)
        #expect(ModelCandidateRules.verb(facts(.notHere, key: nil)) == nil)
    }

    @Test("the Usable words say Now, After download with its size, or why not")
    func words() {
        #expect(ModelCandidateRules.usableWords(facts(.installed)) == "Now")
        #expect(ModelCandidateRules.usableWords(facts(.download)) == "After download (2.1 GB)")
        #expect(ModelCandidateRules.usableWords(facts(.download, refused: "no model for this language"))
                == "no model for this language")
        #expect(ModelCandidateRules.usableWords(facts(.elsewhere)) == "Runs elsewhere")
    }
}
