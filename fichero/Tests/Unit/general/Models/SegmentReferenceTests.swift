@testable import Fichero
import Testing

/// Parsing a `fichero:segment/…` URL (#5164). What breaks without these: a reference opened as a
/// library folder (what the handler did before), a pairing link taken for a reference, or a malformed
/// one resolved with a part missing.
struct SegmentReferenceTests {
    private func parse(_ string: String) -> SegmentReference? {
        SegmentReference.parse(string: string)
    }

    @Test func theStringFormParsesIntoItsThreeParts() {
        let reference = parse("fichero:segment/lib-1/doc-2/seg-3")
        #expect(reference == SegmentReference(libraryId: "lib-1", documentId: "doc-2", segmentId: "seg-3"))
        #expect(reference?.string == "fichero:segment/lib-1/doc-2/seg-3", "sent to the resolver whole")
    }

    @Test func theSlashSlashFormSomeAppsWriteParsesTheSame() {
        #expect(parse("fichero://segment/lib-1/doc-2/seg-3")?.segmentId == "seg-3")
    }

    @Test func otherFicheroLinksAreNotReferences() {
        #expect(parse("fichero://pair?host=a&token=b") == nil)
        #expect(parse("fichero:segment/lib-1/doc-2") == nil, "a part missing")
        #expect(parse("fichero:segment/lib-1//seg-3") == nil, "an empty part")
        #expect(parse("fichero:segment/lib-1/doc-2/seg-3/extra") == nil)
        #expect(parse("https://example.org/segment/lib-1/doc-2/seg-3") == nil)
        #expect(parse("file:///Users/me/Library.fichero") == nil)
    }
}
