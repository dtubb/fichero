@testable import Fichero
import Foundation
import Testing

@Suite("ChecklistItem")
struct ChecklistItemTests {

    @Test("item state and notes survive a Codable round trip")
    func codingRoundTrip() throws {
        let item = ChecklistItem(
            id: "check-1",
            label: "Verify citations",
            checked: true,
            notes: "Checked against source PDF"
        )

        let decoded = try JSONDecoder().decode(ChecklistItem.self, from: JSONEncoder().encode(item))

        #expect(decoded == item)
        #expect(decoded.id == "check-1")
        #expect(decoded.checked)
        #expect(decoded.notes == "Checked against source PDF")
    }
}
