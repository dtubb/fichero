@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// The last unproven hop in the claim-change chain: a decoded `claim.updated`
/// must actually reach a registered `ClaimStore` and move its `changeToken`.
///
/// ## Why this test exists
///
/// "A prune loses nothing" was proven up to the wire and no further. The engine
/// side has `test_prune_trivial_writes_action_audit_and_emits` (prune →
/// `emit_change`) and `test_stream_delivers_matching_library_change`
/// (`emit_change` → SSE subscriber). On the Swift side
/// `LibraryChangeStreamDecodeTests` and `...TransportTests` cover framing and
/// decoding — but nothing drove `apply()` on a real store, so the final hop
/// from a decoded event to a store's observable state was assumed.
///
/// It matters because `changeToken` is what the not-yet-store-backed surfaces
/// observe — the ontology browser's cross-document merge, the inspector's
/// grouped read. If this hop is broken, a library-wide prune leaves every other
/// claim surface stale until a manual reload, and "one redundant fetch" would
/// really have been "silently stale data".
///
/// ## Why it does not simply call `apply()`
///
/// Calling `store.apply(event)` directly would pass whatever the routing did,
/// including nothing. So every case here goes through `LibraryChangeStream`,
/// and the two NEGATIVE tests are what give the positive one its meaning: a
/// wrong-domain event and a self-echo event must NOT move the token. A direct
/// `apply()` would bump in all three.
@MainActor
final class ClaimChangeDeliveryTests: XCTestCase {

    /// Never connects. `ingest` is the out-of-band entry point and does not
    /// touch the transport, but the stream requires one to exist.
    private struct NeverConnectsTransport: ChangeStreamTransport {
        func connect(_ request: URLRequest) async throws
            -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
            throw CocoaError(.fileNoSuchFile)
        }
    }

    private static let windowUnderTest = "window-under-test"

    private func makeStream() -> LibraryChangeStream {
        LibraryChangeStream(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/test.fichero",
            windowId: Self.windowUnderTest,
            transport: NeverConnectsTransport()
        )
    }

    private func makeClaimStore() -> ClaimStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = []
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
        return ClaimStore(
            entityService: EntityService(ficheroClient: client),
            kgCurationService: KGCurationService(ficheroClient: client),
            libraryPath: "/tmp/test.fichero"
        )
    }

    /// Decoded from JSON rather than constructed, so the decode step the real
    /// stream performs is part of what this exercises.
    private func decodeEvent(
        type: String,
        claimIds: [String] = [],
        originWindow: String? = nil
    ) throws -> ChangeEvent {
        let ids = claimIds.map { "\"\($0)\"" }.joined(separator: ", ")
        var fields = [
            "\"type\": \"\(type)\"",
            "\"entity_ids\": []",
            "\"claim_ids\": [\(ids)]",
            "\"document_ids\": []",
            "\"citation_ids\": []",
            "\"reference_ids\": []",
            "\"actor\": \"someone\""
        ]
        if let originWindow {
            fields.append("\"origin_window\": \"\(originWindow)\"")
        }
        let json = "{" + fields.joined(separator: ", ") + "}"
        return try JSONDecoder().decode(ChangeEvent.self, from: Data(json.utf8))
    }

    // MARK: - The hop that was unproven

    func testAClaimUpdatedEventReachesTheRegisteredStoreAndMovesItsToken() throws {
        let store = makeClaimStore()
        let stream = makeStream()
        stream.register(store)
        let before = store.changeToken

        stream.ingest(try decodeEvent(type: "claim.updated", claimIds: ["claim-1"]))

        XCTAssertEqual(
            store.changeToken, before &+ 1,
            "a decoded claim.updated must reach ClaimStore.apply — this is the hop "
                + "every non-store-backed claim surface depends on after a prune"
        )
    }

    /// A prune emits `claim.updated`, but deletion is the other verb the store
    /// handles, and it must also be delivered.
    func testAClaimDeletedEventAlsoMovesTheToken() throws {
        let store = makeClaimStore()
        let stream = makeStream()
        stream.register(store)
        let before = store.changeToken

        stream.ingest(try decodeEvent(type: "claim.deleted", claimIds: ["claim-1"]))

        XCTAssertEqual(store.changeToken, before &+ 1)
    }

    // MARK: - The two negatives that make the positive mean something

    /// Domain filtering really ran. If this bumped, the test above would prove
    /// only that something called `apply`, not that the stream routed by domain.
    func testAnEntityEventDoesNotMoveTheClaimStoreToken() throws {
        let store = makeClaimStore()
        let stream = makeStream()
        stream.register(store)
        let before = store.changeToken

        stream.ingest(try decodeEvent(type: "entity.updated"))

        XCTAssertEqual(
            store.changeToken, before,
            "the stream delivers only domains a consumer declares; ClaimStore takes 'claim'"
        )
    }

    /// Self-echo dedup really ran: an event this window originated is dropped,
    /// so a window does not re-apply its own write.
    func testAnEventThisWindowOriginatedIsNotDeliveredBackToIt() throws {
        let store = makeClaimStore()
        let stream = makeStream()
        stream.register(store)
        let before = store.changeToken

        stream.ingest(
            try decodeEvent(
                type: "claim.updated",
                claimIds: ["claim-1"],
                originWindow: Self.windowUnderTest
            )
        )

        XCTAssertEqual(
            store.changeToken, before,
            "an event tagged with this window's id is this window's own write coming back"
        )
    }

    /// And the same event from ANOTHER window is delivered — otherwise the test
    /// above would pass against a stream that dropped everything.
    func testTheSameEventFromAnotherWindowIsDelivered() throws {
        let store = makeClaimStore()
        let stream = makeStream()
        stream.register(store)
        let before = store.changeToken

        stream.ingest(
            try decodeEvent(
                type: "claim.updated",
                claimIds: ["claim-1"],
                originWindow: "some-other-window"
            )
        )

        XCTAssertEqual(store.changeToken, before &+ 1)
    }
}
