@testable import Fichero
import FicheroAPIClient
import Testing

/// #3869 — the date-entity classifier moved to cached `NSRegularExpression`s. Lock
/// its behaviour so the perf refactor can't quietly change which entities count as
/// dates (they're split out of the named-entity scan).
struct OntologyBrowserDateTests {

    private func entity(_ name: String) -> Components.Schemas.KnowledgeEntity {
        .init(canonicalName: name)
    }

    @Test("Year / numeric-date / month-name prefixes classify as dates")
    func matchesDates() {
        #expect(OntologyBrowser.isDateEntity(entity("1990")))
        #expect(OntologyBrowser.isDateEntity(entity("2020-01-15")))
        #expect(OntologyBrowser.isDateEntity(entity("January 1900")))
        #expect(OntologyBrowser.isDateEntity(entity("Sept 1901")))
        #expect(OntologyBrowser.isDateEntity(entity("dec")))
    }

    @Test("Names, places, and short numbers are not dates")
    func rejectsNonDates() {
        #expect(!OntologyBrowser.isDateEntity(entity("John Smith")))
        #expect(!OntologyBrowser.isDateEntity(entity("Paris")))
        #expect(!OntologyBrowser.isDateEntity(entity("12")))          // fewer than 3 digits
        #expect(!OntologyBrowser.isDateEntity(entity("Marcus")))      // not "mar" boundary
    }
}
