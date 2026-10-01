@testable import Fichero
import Testing

/// #5143, ruled 2026-10-01: File › Import of a TEI, PAGE or ALTO file on its own is one document
/// holding every page, and a page whose image did not come with the file still comes in -- named
/// in the report. What breaks without these: the engine names the pages and the app says nothing,
/// so a person thinks their scans were found; or the list is read off the wrong value type (the
/// generated client hands metadata arrays over as `[(any Sendable)?]`) and is silently empty.
@Suite("Import names the pages that came without an image (#5143)")
struct ImportPagesWithoutImageTests {
    /// The document as `ImportService` makes it: the generated container hands an array over as
    /// `[(any Sendable)?]`, wrapped as `convertMetadata` wraps it, `AnyCodable(value ?? "")`.
    private func imported(_ metadata: [String: (any Sendable)?]) -> Document {
        var wrapped: [String: AnyCodable] = [:]
        for (key, value) in metadata { wrapped[key] = AnyCodable(value ?? "") }
        return Document(id: "doc", docType: .file, fileType: .text, name: "luther.tei.xml", metadata: wrapped)
    }

    @Test("the engine's names are read off the document it returned")
    func readsTheEnginesNames() {
        let names: [(any Sendable)?] = ["page 1 names no image", "page 2 names no image"]
        let document = imported(["pages_without_image": names])
        #expect(ImportOutcome.pagesWithoutImage(in: [document]) == ["page 1 names no image", "page 2 names no image"])
    }

    @Test("the report says every page came in, how many lack an image, and names them")
    func reportNamesThem() throws {
        let names = (1...8).map { "page \($0) names no image" }
        let outcome = ImportOutcome(documents: [], failures: [], attempted: 1, pagesWithoutImage: names)
        let message = try #require(outcome.pagesWithoutImageMessage)
        #expect(message.contains("Every page came in"))
        #expect(message.contains("8 pages have no image"))
        #expect(message.contains("page 1 names no image"))
        #expect(message.contains("(and 2 more)"))
        #expect(outcome.partialFailureMessage == nil, "a page without an image is not a failure")
    }

    @Test("an ordinary import says nothing; a merged drop keeps every page")
    func silentWhenNone() {
        let plain = imported(["ingest_mode": "copy"])
        #expect(ImportOutcome.pagesWithoutImage(in: [plain]).isEmpty)
        #expect(ImportOutcome(documents: [plain], failures: [], attempted: 1).pagesWithoutImageMessage == nil)
        let merged = ImportOutcome.merged([
            ImportOutcome(documents: [], failures: [], attempted: 1, pagesWithoutImage: ["a"]),
            ImportOutcome(documents: [], failures: [], attempted: 1, pagesWithoutImage: ["b"]),
        ])
        #expect(merged.pagesWithoutImage == ["a", "b"])
    }
}
