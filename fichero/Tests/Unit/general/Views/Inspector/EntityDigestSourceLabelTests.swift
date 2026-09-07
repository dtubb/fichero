@testable import Fichero
import XCTest

/// The entity digest's "Appears In" and "Source Annotations" sections showed a
/// raw 32-char source-document id where a page name belongs (Daniel:
/// "68045f58a3ea47b2a4…"). They now resolve the id to a human name via the
/// entity's already-loaded source documents, and NEVER fall back to the raw hash.
final class EntityDigestSourceLabelTests: XCTestCase {

    private func doc(id: String, name: String, parentId: String? = nil) -> Document {
        Document(id: id, parentId: parentId, docType: .file, name: name)
    }

    func test_resolves_name_from_loaded_appears_in_documents() {
        let appearsIn = [doc(id: "68045f58a3ea47b2a4", name: "18590129.pdf")]
        let label = EntityDigestContent.sourceLabel(
            for: "68045f58a3ea47b2a4", appearsIn: appearsIn, storeDocs: []
        )
        XCTAssertEqual(label, "18590129.pdf")
    }

    func test_falls_back_to_store_documents() {
        let store = [doc(id: "abc123", name: "Letter.pdf")]
        let label = EntityDigestContent.sourceLabel(for: "abc123", appearsIn: [], storeDocs: store)
        XCTAssertEqual(label, "Letter.pdf")
    }

    func test_unresolved_id_never_shows_the_raw_hash() {
        let rawId = "68045f58a3ea47b2a4c9d1e0f7"
        let label = EntityDigestContent.sourceLabel(for: rawId, appearsIn: [], storeDocs: [])
        // A short placeholder, not the full id — the whole point of the fix.
        XCTAssertNotEqual(label, rawId)
        XCTAssertFalse(label.contains(String(rawId.suffix(8))), "must not surface the full hash")
        XCTAssertTrue(label.hasPrefix("Source "))
    }

    func test_empty_id_is_named_not_blank() {
        XCTAssertEqual(
            EntityDigestContent.sourceLabel(for: "", appearsIn: [], storeDocs: []),
            "Unknown source"
        )
    }

    func test_appears_in_wins_over_store_for_same_id() {
        // The loaded source docs are the authoritative names for these sections.
        let appearsIn = [doc(id: "d1", name: "Diary 1859.pdf")]
        let store = [doc(id: "d1", name: "fichero_upload_tmp.pdf")]
        let label = EntityDigestContent.sourceLabel(for: "d1", appearsIn: appearsIn, storeDocs: store)
        XCTAssertEqual(label, "Diary 1859.pdf")
    }
}
