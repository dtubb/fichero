@testable import Fichero
import Testing

/// The Inspector's Text section (ruled 2026-09-27, `build-notes-inspector.md` 5.1). What breaks
/// without these: a machine's unchecked guess shown as "the text" (the basis dropped), a retracted
/// reading still listed as a live one, or half of a sic/corr pair shown alone.
struct InspectorTextTests {
    private func reading(
        _ id: String, kind: String = "transcription", content: String = "", maker: String = "workflow",
        pair: String? = nil, role: String? = nil
    ) -> InspectorText.Reading {
        .init(id: id, kind: kind, content: content, maker: maker, author: nil, guideline: nil, pairId: pair, pairRole: role)
    }

    @Test("every basis the contract names has its own words, and an unknown one is shown as itself")
    func basisIsNeverDropped() {
        #expect(InspectorText.Why(basis: "chosen") == .chosen)
        #expect(InspectorText.Why(basis: "newest-human") == .newestHuman)
        #expect(InspectorText.Why(basis: "newest-machine-unchosen") == .newestMachineUnchosen)
        #expect(InspectorText.Why(basis: "none") == .noneCounts)
        #expect(InspectorText.Why(basis: nil) == .noneCounts)
        #expect(InspectorText.Why(basis: "by-committee") == .unknown("by-committee"))
        #expect(InspectorText.Why.newestMachineUnchosen.label.contains("not yet checked"))
        #expect(InspectorText.Why.unknown("by-committee").label.contains("by-committee"))
    }

    @Test("a retracted reading is left out; the counting one is marked per kind")
    func retractedLeftOutCountingMarked() {
        let text = InspectorText(
            readings: [reading("r1"), reading("r2"), reading("r3"), reading("t1", kind: "translation")],
            retracted: ["r2"],
            counting: [
                "transcription": .init(readingId: "r3", why: .chosen),
                "translation": .init(readingId: nil, why: .noneCounts)
            ]
        )
        #expect(text.readings.map(\.id) == ["r1", "r3", "t1"])
        #expect(text.kinds == ["transcription", "translation"])
        #expect(text.readings(ofKind: "transcription").map(\.id) == ["r1", "r3"])
        #expect(text.counts(text.readings[1]))
        #expect(!text.counts(text.readings[0]))
        #expect(!text.counts(text.readings[2]))
    }

    @Test("a written / read pair is shown as a pair")
    func pairsFindTheirPartner() {
        let sic = reading("s", content: "recieve", pair: "p1", role: "sic")
        let corr = reading("c", content: "receive", pair: "p1", role: "corr")
        let alone = reading("a")
        let text = InspectorText(readings: [sic, corr, alone], counting: [:])
        #expect(text.partner(of: sic) == corr)
        #expect(text.partner(of: corr) == sic)
        #expect(text.partner(of: alone) == nil)
    }
}
