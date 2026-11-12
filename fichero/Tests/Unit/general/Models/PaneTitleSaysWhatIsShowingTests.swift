@testable import Fichero
import Foundation
import Testing

/// #6458, `source.editor.pane-title-says-what-is-showing`: the lens title says what is showing when there is room
/// (full "Content · Claude Sonnet · as written ✓"), shortens to the reader ("Content · Claude Sonnet"), then to the lens name.
@Suite("The pane title says what is showing (#6458)")
struct PaneTitleSaysWhatIsShowingTests {
    @Test("one reader, a level and a person's check give the three forms")
    func threeForms() {
        let title = PaneTitleForms(lens: "Content", makers: ["Claude Sonnet"], level: "as written", basis: .person)
        #expect(title.full == "Content · Claude Sonnet · as written ✓")
        #expect(title.middle == "Content · Claude Sonnet")
        #expect(title.short == "Content")
        #expect(title.tooltip == title.full)
    }

    @Test("two makers read '2 readers'")
    func manyReaders() {
        let title = PaneTitleForms(lens: "Content", makers: ["Claude Sonnet", "ann", "Claude Sonnet"], level: "as written", basis: .person)
        #expect(title.full == "Content · 2 readers · as written ✓")
        #expect(title.middle == "Content · 2 readers")
    }

    @Test("a machine's unchecked reading shows the hollow circle, none counting shows a dash")
    func basisGlyphs() {
        #expect(PaneTitleForms(lens: "Lines", makers: ["kraken"], level: nil, basis: .machine).full == "Lines · kraken · as written ○")
        #expect(PaneTitleForms(lens: "Lines", makers: ["kraken"], level: "modernised", basis: .none).full == "Lines · kraken · modernised –")
    }

    @Test("a lens with no reading says only its name at every width")
    func noReading() {
        let title = PaneTitleForms(lens: "Content", makers: [], level: nil, basis: .none)
        #expect(title.full == "Content")
        #expect(title.middle == "Content")
        #expect(title.short == "Content")
    }

    @Test("the disagreement lens shortens to readers and agreement, then the lens name")
    func disagreement() {
        let title = PaneTitleForms.disagreement(lens: "Where the Readers Disagree", readers: 3, agreementPercent: 82)
        #expect(title.full == "Where the Readers Disagree · 3 readers · 82 %")
        #expect(title.middle == "3 readers · 82 %")
        #expect(title.short == "Where the Readers Disagree")
        #expect(title.tooltip == title.full)
    }
}
