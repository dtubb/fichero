@testable import Fichero
import Foundation
import Testing

/// #4418: the two halves of the geometry feature never met.
///
/// `OCRGeometryOverlay` asked for artifacts of `type: "transcription"`; the
/// import path writes `artifact_type = "text_geometry"`. Two green commits and
/// a dead feature — invisible to the toolchain because `artifact_type` is a
/// bare `str` in the OpenAPI schema, so no string can be wrong.
///
/// The second half is worse than the identifier. Selection was
/// `max(by: createdAt)`, which answers "what happened most recently" rather
/// than "what carries page boxes".
///
/// And the producer forces the issue: `_save_pdf_text_layer_geometry` writes a
/// `text_geometry` artifact **even for a page with no text layer**, carrying
/// zero boxes, so a scan stays distinguishable from an unprocessed page. Any
/// rule that merely prefers `text_geometry` would therefore blind every scanned
/// page — fixing born-digital PDFs by breaking the images that worked. These
/// tests pin the rule that serves both.
struct OCRGeometrySelectionTests {

    private func artifact(
        id: String,
        type: String,
        ageInHours: Double,
        boxCount: Int? = nil
    ) -> Artifact {
        Artifact(
            id: id,
            documentId: "page-1",
            artifactType: type,
            data: boxCount.map { ["box_count": AnyCodable($0)] },
            createdAt: Date(timeIntervalSince1970: 1_000_000 - ageInHours * 3600)
        )
    }

    // MARK: - The identifier

    /// The vocabulary must include the type the server actually writes. This is
    /// the assertion that would have failed the day the mismatch was authored.
    @Test("the type the importer writes is one the client asks for")
    func theProducersTypeIsRequested() {
        #expect(OCRGeometrySelection.geometryBearingTypes.contains("text_geometry"))
    }

    /// Transcription is kept, not replaced. OCR'd scans deliver their boxes
    /// under that type and are the reason the overlay existed at all (#4309).
    @Test("transcription remains a source, ranked below the PDF's own text layer")
    func transcriptionRemainsASource() {
        let types = OCRGeometrySelection.geometryBearingTypes
        #expect(types.contains("transcription"))
        #expect(types.firstIndex(of: "text_geometry")! < types.firstIndex(of: "transcription")!)
    }

    // MARK: - The recency defect, stated directly

    /// The exact regression: a transcription run happens AFTER import, so it is
    /// newer than the geometry artifact. Under `max(by: createdAt)` it won.
    @Test("a newer transcription does not displace the page's own text layer")
    func newerTranscriptionDoesNotDisplaceGeometry() {
        let geometry = artifact(id: "geo", type: "text_geometry", ageInHours: 48, boxCount: 120)
        let transcription = artifact(id: "ocr", type: "transcription", ageInHours: 1, boxCount: 90)

        let ranked = OCRGeometrySelection.ranked([transcription, geometry])

        #expect(ranked.first?.id == "geo")
        #expect(ranked.map(\.id) == ["geo", "ocr"])
    }

    /// Generalised: whatever the timestamps, authority beats recency.
    @Test("authority beats recency at every age")
    func authorityBeatsRecencyAtEveryAge() {
        for age in [0.0, 1, 100, 10_000] {
            let ranked = OCRGeometrySelection.ranked([
                artifact(id: "ocr", type: "transcription", ageInHours: 0, boxCount: 5),
                artifact(id: "geo", type: "text_geometry", ageInHours: age, boxCount: 5)
            ])
            #expect(ranked.first?.id == "geo", Comment(rawValue: "age \(age)"))
        }
    }

    /// Recency survives only as a tie-break within one type — re-running OCR
    /// should still prefer the latest OCR.
    @Test("recency still breaks ties inside a single type")
    func recencyBreaksTiesWithinAType() {
        let ranked = OCRGeometrySelection.ranked([
            artifact(id: "old", type: "transcription", ageInHours: 10, boxCount: 5),
            artifact(id: "new", type: "transcription", ageInHours: 1, boxCount: 5)
        ])
        #expect(ranked.map(\.id) == ["new", "old"])
    }

    // MARK: - The trap the obvious fix would have opened

    /// A scanned page: the importer wrote an EMPTY `text_geometry` artifact by
    /// design, and OCR later produced the real boxes. Preferring the type alone
    /// would show nothing here — the images-for-PDFs trade.
    @Test("a scan's empty geometry artifact yields to the OCR that has boxes")
    func emptyGeometryArtifactYieldsToOCR() {
        let empty = artifact(id: "geo-empty", type: "text_geometry", ageInHours: 48, boxCount: 0)
        let ocr = artifact(id: "ocr", type: "transcription", ageInHours: 1, boxCount: 90)

        let ranked = OCRGeometrySelection.ranked([empty, ocr])

        #expect(ranked.map(\.id) == ["ocr"])
        #expect(
            !ranked.contains(where: { $0.id == "geo-empty" }),
            "a zero-box artifact is not a source"
        )
    }

    /// Only an explicit zero disqualifies. A transcription artifact carries no
    /// `box_count` at all, and absence of the hint is not evidence of absence
    /// of boxes — dropping those would blind every OCR'd page.
    @Test("an artifact with no box count is still probed")
    func unknownBoxCountIsStillProbed() {
        let ranked = OCRGeometrySelection.ranked([
            artifact(id: "unknown", type: "transcription", ageInHours: 1)
        ])
        #expect(ranked.map(\.id) == ["unknown"])
        #expect(!OCRGeometrySelection.isKnownEmpty(ranked[0]))
    }

    @Test("a zero box count is recognised however the payload typed it")
    func zeroBoxCountIsRecognised() {
        #expect(OCRGeometrySelection.isKnownEmpty(
            artifact(id: "a", type: "text_geometry", ageInHours: 1, boxCount: 0)))
        #expect(!OCRGeometrySelection.isKnownEmpty(
            artifact(id: "b", type: "text_geometry", ageInHours: 1, boxCount: 1)))
        // JSON numbers can decode as Double; a Double zero is still empty.
        var asDouble = artifact(id: "c", type: "text_geometry", ageInHours: 1)
        asDouble.data = ["box_count": AnyCodable(0.0)]
        #expect(OCRGeometrySelection.isKnownEmpty(asDouble))
    }

    // MARK: - Unrelated artifacts are never considered

    /// The document also carries summaries, entities, translations. None of
    /// them can supply geometry, and probing them would spend a fetch each.
    @Test("artifacts of other types are not candidates")
    func otherTypesAreNotCandidates() {
        let ranked = OCRGeometrySelection.ranked([
            artifact(id: "sum", type: "summary", ageInHours: 0),
            artifact(id: "ent", type: "entities", ageInHours: 0),
            artifact(id: "tab", type: "kreuzberg_table", ageInHours: 0),
            artifact(id: "geo", type: "text_geometry", ageInHours: 5, boxCount: 3)
        ])
        #expect(ranked.map(\.id) == ["geo"])
    }

    @Test("no candidates yields nothing rather than a wrong guess")
    func noCandidatesYieldsNothing() {
        #expect(OCRGeometrySelection.ranked([]).isEmpty)
        #expect(OCRGeometrySelection.ranked([
            artifact(id: "sum", type: "summary", ageInHours: 0)
        ]).isEmpty)
    }

    // MARK: - The final word is the payload

    /// Type and rank get an artifact probed; only boxes make it the answer.
    @Test("only real boxes count as geometry")
    func onlyRealBoxesCount() {
        #expect(!OCRGeometrySelection.carriesGeometry(nil))
        #expect(!OCRGeometrySelection.carriesGeometry(
            OCRGeometry(text: "", provider: "pymupdf", model: nil, boxes: [])))
        #expect(OCRGeometrySelection.carriesGeometry(
            OCRGeometry(
                text: "hello",
                provider: "pymupdf",
                model: nil,
                boxes: [OCRGeometryBox(
                    text: "hello", bbox: [0, 0, 0.1, 0.1], level: "word", confidence: nil,
                    pageIndex: 0, charStart: 0, charEnd: 5
                )]
            )))
    }

    // MARK: - Structural: the overlay uses the shared decision

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func codeOnly(_ source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// The loader must not re-inline either decision. Comments are stripped
    /// first: the ones there deliberately name the old shape.
    @Test("the overlay defers both the vocabulary and the ranking")
    func theOverlayDefersTheDecision() throws {
        let source = try Self.codeOnly(
            Self.appSource("Views/Preview/ImageViewer/OCRGeometryOverlay.swift"))

        #expect(source.contains("OCRGeometrySelection.geometryBearingTypes"))
        #expect(source.contains("OCRGeometrySelection.ranked("))
        #expect(source.contains("OCRGeometrySelection.carriesGeometry("))

        // The two defects, in their original code form.
        #expect(!source.contains("max(by: { $0.createdAt < $1.createdAt })"))
        #expect(!source.contains("type: \"transcription\""))
    }

    /// The server's vocabulary must live in exactly one place, so adopting a
    /// generated enum later is a rename and not a hunt.
    @Test("the artifact type literals appear only in the selection type")
    func vocabularyLivesInOnePlace() throws {
        let overlay = try Self.codeOnly(
            Self.appSource("Views/Preview/ImageViewer/OCRGeometryOverlay.swift"))
        #expect(!overlay.contains("\"text_geometry\""))
        #expect(!overlay.contains("\"transcription\""))

        let selection = try Self.appSource("Models/OCRGeometrySelection.swift")
        #expect(selection.contains("\"text_geometry\""))
    }

    /// #4426: `Artifact.ArtifactType` is a hand-rolled shadow of the server's
    /// vocabulary — 8 cases against the 20+ actually written. The fix must not
    /// deepen it. When `artifact_type` becomes a declared enum in the schema,
    /// the generated type replaces both.
    @Test("the fix does not widen the hand-rolled shadow enum")
    func theShadowEnumIsNotWidened() throws {
        let artifact = try Self.appSource("Models/Artifact.swift")
        let shadow = artifact.components(separatedBy: "enum ArtifactType: String {")[1]
            .components(separatedBy: "}")[0]
        #expect(!shadow.contains("textGeometry"))
        #expect(!shadow.contains("text_geometry"))
    }
}
