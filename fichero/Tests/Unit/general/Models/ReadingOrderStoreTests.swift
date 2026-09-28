@testable import Fichero
import Testing

/// Q5 (ruled 2026-09-27): reorder in the Reader, the Inspector and the Segments pane, by drag and
/// by keys, with ONE implementation -- this store, through `ReadingOrderMove`, into the one
/// `POST /api/reading-orders/{id}/place`. What breaks without these: a key and a drag that move
/// differently, a no-op move written to the audit trail, or a list that shows a move the engine
/// refused.
@MainActor
struct ReadingOrderStoreTests {
    @MainActor
    final class FakeTransport: ReadingOrderTransport {
        var orderList: [ReadingOrderSummary] = [
            .init(id: "o-imposed", name: "commentary first", kind: "imposed"),
            .init(id: "o-written", name: "as-written", kind: "as-written")
        ]
        var entryList: [ReadingOrderMove.Entry] = [
            .init(entryId: "e-a", segmentId: "s-a", version: 1),
            .init(entryId: "e-b", segmentId: "s-b", version: 1),
            .init(entryId: "e-c", segmentId: "s-c", version: 1)
        ]
        /// Block `s-b`'s lines, the level below the top (entry `e-b`).
        var linesOfB: [ReadingOrderMove.Entry] = [
            .init(entryId: "e-l1", segmentId: "s-l1", version: 1, parentEntryId: "e-b"),
            .init(entryId: "e-l2", segmentId: "s-l2", version: 1, parentEntryId: "e-b"),
            .init(entryId: "e-l3", segmentId: "s-l3", version: 1, parentEntryId: "e-b")
        ]
        /// Line `s-l2`'s words (ruled 2026-09-27: words reorder under a line with the same verbs).
        var wordsOfL2: [ReadingOrderMove.Entry] = [
            .init(entryId: "e-w1", segmentId: "s-w1", version: 1, parentEntryId: "e-l2"),
            .init(entryId: "e-w2", segmentId: "s-w2", version: 1, parentEntryId: "e-l2")
        ]
        var sent: [ReadingOrderMove.Place] = []
        var failWith: Error?
        /// How many levels were read, so a no-op can be seen to read nothing.
        var entriesCalls = 0

        func orders(documentId: String) async throws -> [ReadingOrderSummary] { orderList }
        func entries(orderId: String, parentEntryId: String?) async throws -> [ReadingOrderMove.Entry] {
            entriesCalls += 1
            return switch parentEntryId {
            case nil: entryList
            case "e-b": linesOfB
            case "e-l2": wordsOfL2
            default: []
            }
        }
        func place(_ place: ReadingOrderMove.Place) async throws -> String? {
            if let failWith { throw failWith }
            sent.append(place)
            return "audit-\(sent.count)"
        }
    }

    private func loaded() async throws -> (ReadingOrderStore, FakeTransport) {
        let transport = FakeTransport()
        let store = ReadingOrderStore(transport: transport)
        try await store.load(documentId: "d1")
        return (store, transport)
    }

    /// The picker's choice (#5160; `check_store_wholesale_reload`): picking the order already shown
    /// must not re-read and replace the list -- that is the wholesale reload the guard forbids, and it
    /// would throw away the level the person opened. Another order does replace it: a new list.
    @Test("choosing the order already shown re-reads nothing and keeps the level; another order replaces the list")
    func choosingTheShownOrderIsANoOp() async throws {
        let (store, transport) = try await loaded()
        await store.show(childrenOf: "s-b")
        let calls = transport.entriesCalls
        try await store.choose("o-written")
        #expect(transport.entriesCalls == calls, "nothing re-read")
        #expect(store.shown.map(\.segmentId) == ["s-l1", "s-l2", "s-l3"], "the level opened stays")
        try await store.choose("o-imposed")
        #expect(store.orderId == "o-imposed")
        #expect(transport.entriesCalls == calls + 1)
        #expect(store.shown.map(\.segmentId) == ["s-a", "s-b", "s-c"], "another order shows its own top level")
    }

    @Test("the file's own order is shown first")
    func loadsAsWritten() async throws {
        let (store, _) = try await loaded()
        #expect(store.orderId == "o-written")
        #expect(store.entries.map(\.segmentId) == ["s-a", "s-b", "s-c"])
    }

    @Test("a key sends ONE place, and the list shows the move with the row's new version")
    func keyMoveIsOneCallAppliedInPlace() async throws {
        let (store, transport) = try await loaded()
        let audit = await store.move("s-c", step: .upward)
        #expect(audit == "audit-1")
        #expect(transport.sent == [.init(orderId: "o-written", segmentId: "s-c", afterEntryId: "e-a", expectedVersion: 1)])
        #expect(store.entries.map(\.segmentId) == ["s-a", "s-c", "s-b"])
        #expect(store.entries[1].version == 2)
    }

    @Test("a drag and a key to the same place send the same request")
    func dragEqualsKey() async throws {
        let (byKey, keyTransport) = try await loaded()
        let (byDrag, dragTransport) = try await loaded()
        await byKey.move("s-a", step: .toEnd)
        await byDrag.move("s-a", to: 2)
        #expect(keyTransport.sent == dragTransport.sent)
        #expect(byKey.entries.map(\.segmentId) == byDrag.entries.map(\.segmentId))
    }

    @Test("a move to where it already is sends nothing")
    func noOpSendsNothing() async throws {
        let (store, transport) = try await loaded()
        #expect(await store.move("s-a", step: .upward) == nil)
        #expect(transport.sent.isEmpty)
        #expect(store.lastRefusal != nil)
    }

    @Test("a move the engine refuses leaves the list as it was, and says why")
    func refusedMoveChangesNothing() async throws {
        let (store, transport) = try await loaded()
        transport.failWith = ReadingOrderError.movedMeanwhile
        #expect(await store.move("s-c", step: .toStart) == nil)
        #expect(store.entries.map(\.segmentId) == ["s-a", "s-b", "s-c"])
        #expect(store.lastRefusal?.contains("movedMeanwhile") == true)
    }

    @Test("the Reader and the Inspector send the SAME place for the same move of a line")
    func readerAndInspectorSendTheSamePlace() async throws {
        // What breaks without it: a line moved from the Reader's text would be lifted out of its
        // block (no parent sent means the top level), or move differently from the Inspector's key.
        let (inspector, inspectorTransport) = try await loaded()
        await inspector.move("s-l2", step: .upward)

        let readerTransport = FakeTransport()
        let reader = ReadingOrderStore(transport: readerTransport)
        let body: [String: Any] = ["segmentId": "s-l2", "pageId": "d1", "step": "up"]
        let request = try #require(ReaderLineMove.request(from: body))
        await ReaderLineMove.perform(request, store: reader)

        let expected = ReadingOrderMove.Place(
            orderId: "o-written", segmentId: "s-l2", afterEntryId: nil, expectedVersion: 1, parentEntryId: "e-b"
        )
        #expect(inspectorTransport.sent == [expected])
        #expect(readerTransport.sent == inspectorTransport.sent)
    }

    @Test("a line moves within its block, and the top of the order is left alone")
    func aLineMovesWithinItsBlock() async throws {
        let (store, transport) = try await loaded()
        await store.move("s-l1", step: .toEnd)
        #expect(transport.sent.first?.afterEntryId == "e-l3")
        #expect(transport.sent.first?.parentEntryId == "e-b")
        #expect(store.entries.map(\.segmentId) == ["s-a", "s-b", "s-c"])
        // The level was applied in place: a second key press plans from the moved line's new spot.
        await store.move("s-l1", step: .upward)
        #expect(transport.sent.last?.afterEntryId == "e-l2")
    }

    @Test("a malformed message from the page moves nothing")
    func malformedMessageMovesNothing() {
        #expect(ReaderLineMove.request(from: ["segmentId": "s-l2", "pageId": "d1", "step": "sideways"]) == nil)
        #expect(ReaderLineMove.request(from: ["segmentId": "", "pageId": "d1", "step": "up"]) == nil)
        #expect(ReaderLineMove.request(from: ["segmentId": "s-l2", "step": "up"]) == nil)
        #expect(["up", "down", "toStart", "toEnd"].compactMap(ReaderLineMove.step(named:)) == [.upward, .downward, .toStart, .toEnd])
    }

    @Test("a segment in no level of the order is refused, with nothing sent")
    func unknownSegmentIsRefused() async throws {
        let (store, transport) = try await loaded()
        #expect(await store.move("s-nowhere", step: .upward) == nil)
        #expect(transport.sent.isEmpty)
        #expect(store.lastRefusal?.contains("notInThisOrder") == true)
    }

    @Test("the Order section lists the inspected segment's children, and a drag there stays in that level")
    func showsChildrenAndDragsWithinThem() async throws {
        let (store, transport) = try await loaded()
        await store.show(childrenOf: "s-b")
        #expect(store.shown.map(\.segmentId) == ["s-l1", "s-l2", "s-l3"])
        await store.move("s-l3", to: 0)
        #expect(transport.sent.last?.parentEntryId == "e-b")
        #expect(transport.sent.last?.afterEntryId == nil)
        #expect(store.shown.map(\.segmentId) == ["s-l3", "s-l1", "s-l2"])
        #expect(store.entries.map(\.segmentId) == ["s-a", "s-b", "s-c"])   // the top is untouched
    }

    @Test("words under a line are listed and moved with the same verbs as lines")
    func wordsReorderUnderTheirLine() async throws {
        let (store, transport) = try await loaded()
        await store.show(childrenOf: "s-l2")
        #expect(store.shown.map(\.segmentId) == ["s-w1", "s-w2"])
        await store.move("s-w2", step: .upward)
        #expect(transport.sent.last == .init(
            orderId: "o-written", segmentId: "s-w2", afterEntryId: nil, expectedVersion: 1, parentEntryId: "e-l2"
        ))
    }

    @Test("a segment the order does not hold shows NOTHING, never the top in its place; nil shows the top")
    func unknownParentShowsNothing() async throws {
        let (store, _) = try await loaded()
        await store.show(childrenOf: "s-nowhere")
        #expect(store.shown.isEmpty)
        await store.show(childrenOf: nil)
        #expect(store.shown.map(\.segmentId) == ["s-a", "s-b", "s-c"])
    }
}
