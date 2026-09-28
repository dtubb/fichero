@testable import Fichero
import Testing

/// The Inspector's Signs section (5.6). What breaks without these: a sign the segment uses left out
/// (or one it does not use listed), a list number shown as a code point, or a letterform whose
/// allograph or hand is shown by its id.
struct InspectorSignsTests {
    private let mufi = InspectorSigns.Sign(
        id: "s1", name: "MUFI abbreviation sign", pictureSegmentId: "seg-1", codePoint: "U+F1AC",
        listReferences: [.init(authority: "MUFI", number: "F1AC")]
    )

    @Test("a sign is listed where the segment USES it or was DECLARED from, with how often")
    func rowsForTheSegment() {
        let uses = "a \u{F1AC} b \u{F1AC}"
        let here = InspectorSigns.rows(signs: [mufi], segmentId: "seg-2", reading: uses, usedInProject: ["s1": 50])
        #expect(here == [InspectorSigns.Row(
            signId: "s1", title: "MUFI abbreviation sign", detail: "U+F1AC · MUFI F1AC · 2 here · 50 in the project",
            glyph: "\u{F1AC}"
        )])
        #expect(InspectorSigns.rows(signs: [mufi], segmentId: "seg-2", reading: "plain").isEmpty)
        let declared = InspectorSigns.rows(signs: [mufi], segmentId: "seg-1", reading: nil)
        #expect(declared.map(\.detail) == ["U+F1AC · MUFI F1AC · declared from this segment"])
    }

    @Test("a sign known only by its list number has no glyph; a variant says so")
    func numberOnlyAndVariants() {
        let numbered = InspectorSigns.Sign(
            id: "s2", name: "Linear B sign", pictureSegmentId: "seg-1", codePoint: nil,
            listReferences: [.init(authority: "Bennett", number: "*56")]
        )
        let variant = InspectorSigns.Sign(
            id: "s3", name: "long s", pictureSegmentId: "seg-1", codePoint: "U+017F", variantOf: "s", variant: "long"
        )
        let rows = InspectorSigns.rows(signs: [numbered, variant], segmentId: "seg-1", reading: nil)
        #expect(rows.map(\.glyph) == [nil, "ſ"])
        #expect(rows.map(\.detail) == [
            "Bennett *56 · declared from this segment", "U+017F · a variant of s (long) · declared from this segment"
        ])
        #expect(InspectorSigns.character(of: "F1AC") == nil, "not a code point without U+")
    }

    @Test("a letterform reads character › allograph › hand, then its features and who described it")
    func letterformLines() {
        let lines = InspectorSigns.lines(
            [.init(id: "d1", character: "ܐ", allographId: "a1", handId: "h1",
                   features: [(component: "stem", feature: "wedged")], describedBy: "owner")],
            allographs: ["a1": "Estrangela alaph"], hands: [:]
        )
        #expect(lines == [.init(descriptionId: "d1", chain: "ܐ › Estrangela alaph › an unlisted hand",
                                detail: "stem wedged · by owner")])
    }
}
