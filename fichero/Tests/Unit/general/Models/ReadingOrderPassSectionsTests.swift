@testable import Fichero
import Foundation
import Testing

/// Two passes, two Layout Orders (#6421, `source.editor.orders.say-where-they-came-from`): the picker lists the working
/// pass's orders first, then the other passes' under "From other passes", each saying which pass made it.
struct ReadingOrderPassSectionsTests {
    private let format = Date.FormatStyle(date: .abbreviated, time: .omitted, locale: Locale(identifier: "en_US"),
                                          timeZone: TimeZone(identifier: "UTC") ?? .current)

    private func pass(_ id: String, model: String? = nil, file: String? = nil, at seconds: Double? = nil) -> SegmentPassValue {
        var made = SegmentPassValue(
            id: id, provisional: false, documentId: "p1", name: "text_geometry", provenanceKind: .workflow,
            provider: nil, model: model, runId: nil, createdAt: seconds.map { Date(timeIntervalSince1970: $0) }, text: nil,
            sourceArtifactId: nil, artifactType: nil
        )
        made.importFile = file
        return made
    }

    private let orders = [
        ReadingOrderSummary(id: "o1", name: "as-written", kind: "as-written", passId: "kraken"),
        ReadingOrderSummary(id: "o2", name: "Margins first", kind: "imposed", passId: "kraken"),
        ReadingOrderSummary(id: "o3", name: "as-written", kind: "as-written", passId: "file", provenanceKind: "external_import")
    ]

    @Test("the working pass's orders come first, its Layout Order saying it is the one shown; the other pass's are named")
    func twoPassesTwoLayoutOrders() {
        let sections = ReadingOrderChoice.sections(
            orders, workingPassId: "kraken",
            passes: [pass("kraken", model: "kraken", at: 1_762_560_000), pass("file", file: "0065.xml", at: 1_762_473_600)],
            format: format
        )
        #expect(sections.thisPass.map(\.title) == ["Layout Order · shown on the page", "Margins first"])
        #expect(sections.otherPasses.map(\.title) == ["Order: As in the File · from 0065.xml, Nov 7, 2025"])
        #expect(sections.title(of: "o3") == "Order: As in the File · from 0065.xml, Nov 7, 2025")
    }

    @Test("one pass, or no working pass known, lists every order plainly")
    func onePassIsPlain() {
        let plain = ReadingOrderChoice.sections(Array(orders.prefix(2)), workingPassId: "kraken", passes: [], format: format)
        #expect(plain.thisPass.map(\.title) == ["Layout Order", "Margins first"])
        #expect(plain.otherPasses.isEmpty)
        #expect(ReadingOrderChoice.sections(orders, workingPassId: nil, passes: [], format: format).otherPasses.isEmpty)
    }

    @Test("a pass is named by its file, else its model, else its name; the date when known")
    func passLabels() {
        #expect(ReadingOrderChoice.passLabel(pass("a", model: "kraken"), format: format) == "kraken")
        #expect(ReadingOrderChoice.passLabel(pass("b"), format: format) == "text_geometry")
        #expect(ReadingOrderChoice.passLabel(pass("c", model: "kraken", file: "a.xml", at: 0), format: format)
                == "from a.xml, Jan 1, 1970")
    }
}
