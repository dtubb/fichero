@testable import Fichero
import Foundation
import Testing

@Suite("BatchItemInfo")
struct BatchItemInfoTests {

    @Test("decodes snake-case item fields and preserves optional timing data")
    func decodesBackendPayload() throws {
        let data = Data(
            """
            {"thread_id":"thread-1","item_index":2,"inputs":{"document":"doc-1"},
             "status":"failed","error":"rate limited","started_at":"2026-01-01T00:00:00Z",
             "completed_at":"2026-01-01T00:01:00Z"}
            """.utf8
        )

        let item = try JSONDecoder().decode(BatchItemInfo.self, from: data)

        #expect(item.id == "thread-1")
        #expect(item.itemIndex == 2)
        #expect(item.inputs == ["document": "doc-1"])
        #expect(item.status == "failed")
        #expect(item.error == "rate limited")
        #expect(item.startedAt == "2026-01-01T00:00:00Z")
        #expect(item.completedAt == "2026-01-01T00:01:00Z")
    }

    @Test("optional inputs and timestamps round-trip as absent")
    func optionalFieldsRoundTripAbsent() throws {
        let input = BatchItemInfo(
            threadId: "thread-2",
            itemIndex: 0,
            inputs: nil,
            status: "pending",
            error: nil,
            startedAt: nil,
            completedAt: nil
        )

        let decoded = try JSONDecoder().decode(BatchItemInfo.self, from: JSONEncoder().encode(input))

        #expect(decoded.id == "thread-2")
        #expect(decoded.inputs == nil)
        #expect(decoded.startedAt == nil)
        #expect(decoded.completedAt == nil)
    }
}
