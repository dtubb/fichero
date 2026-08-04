@testable import Fichero
import XCTest

/// Covers the parsing logic moved out of `ArtifactEntitiesView` /
/// `ArtifactEntityCell` into the shared `ArtifactEntityStore` (#3861). The N+1
/// fix hinges on `parse` producing the SAME per-type name lists the views used
/// to build inline, so a document visible as a row + up to six type cells reads
/// one shared bundle instead of firing seven `getArtifacts()` calls.
@MainActor
final class ArtifactEntityStoreTests: XCTestCase {
    private func artifact(_ type: String, data: [String: AnyCodable]) -> Artifact {
        Artifact(documentId: "d1", artifactType: type, data: data)
    }

    func testParseMapsEachEntityTypeToItsField() {
        let artifacts = [
            artifact("people", data: ["items": AnyCodable([["name": "Alice"], ["name": "Bob"]])]),
            artifact("places", data: ["items": AnyCodable([["name": "Quibdó"]])]),
            artifact("organizations", data: ["items": AnyCodable([["name": "ACME"]])]),
            artifact("events", data: ["items": AnyCodable([["event": "Flood"]])]),
            artifact("keywords", data: ["keywords": AnyCodable(["war", "peace"])]),
            artifact("dates", data: ["items": AnyCodable([["date_normalized": "1990-01-02"], ["date": "raw"]])])
        ]

        let bundle = ArtifactEntityStore.parse(artifacts)

        XCTAssertEqual(bundle.people, ["Alice", "Bob"])
        XCTAssertEqual(bundle.places, ["Quibdó"])
        XCTAssertEqual(bundle.organizations, ["ACME"])
        XCTAssertEqual(bundle.events, ["Flood"])
        XCTAssertEqual(bundle.keywords, ["war", "peace"])
        // Dates prefer date_normalized, fall back to date.
        XCTAssertEqual(bundle.dates, ["1990-01-02", "raw"])
        XCTAssertFalse(bundle.isEmpty)
    }

    func testParseOfNoEntityArtifactsIsEmpty() {
        // A non-entity artifact type (e.g. transcription) contributes nothing.
        let bundle = ArtifactEntityStore.parse([artifact("transcription", data: [:])])
        XCTAssertTrue(bundle.isEmpty)
        XCTAssertEqual(bundle.people, [])
    }

    // MARK: - Failed reads are a third state, not an empty bundle (#4507)

    private struct TestTransportError: Error {}

    /// Offline store: the client points at a path no engine serves, and these
    /// tests drive the state machine through `apply(fetchOutcome:)` — the seam
    /// the #4507 fix introduced precisely because the old `try?`-swallowing
    /// path was unreachable by any test.
    private func makeStore() -> ArtifactEntityStore {
        ArtifactEntityStore(
            artifactService: ArtifactService(
                ficheroClient: FicheroClient(libraryPath: "/tmp/test-entity-store.fichero")
            )
        )
    }

    func testFailedReadDoesNotCacheAnEmptyBundle() {
        let store = makeStore()

        store.apply(fetchOutcome: .failure(TestTransportError()), for: "d1")

        // The defect: a failed read wrote ArtifactEntityBundle() here, so
        // "couldn't load" rendered as the measured-zero "—" for the session.
        XCTAssertNil(store.bundle(for: "d1"), "a failed read must not claim a measured zero")
        XCTAssertTrue(store.loadFailed(for: "d1"))
    }

    func testMeasuredZeroAndFailedReadStayDistinguishable() {
        let store = makeStore()

        store.apply(fetchOutcome: .success([]), for: "measured")
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "failed")

        XCTAssertEqual(store.bundle(for: "measured")?.isEmpty, true)
        XCTAssertFalse(store.loadFailed(for: "measured"))
        XCTAssertNil(store.bundle(for: "failed"))
        XCTAssertTrue(store.loadFailed(for: "failed"))
    }

    func testEnsureLoadedDoesNotRetryAFailedIdOnItsOwn() {
        // No retry storm: a scroll past a failed row must not re-dial a downed
        // engine. Only invalidate/retryFailedLoads clear the mark.
        let store = makeStore()
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "d1")

        store.ensureLoaded("d1")

        XCTAssertTrue(store.loadFailed(for: "d1"))
        XCTAssertNil(store.bundle(for: "d1"))
    }

    func testInvalidateClearsTheFailedMarkSoTheRetryDecides() {
        let store = makeStore()
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "d1")

        store.invalidate(["d1"])

        // Synchronous half of the contract: the stale failure no longer
        // decides the rendered state; the refetch's own outcome will.
        XCTAssertFalse(store.loadFailed(for: "d1"))
    }

    func testSuccessAfterFailureReplacesTheFailedState() {
        let store = makeStore()
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "d1")

        store.apply(
            fetchOutcome: .success([artifact("people", data: ["items": AnyCodable([["name": "Alice"]])])]),
            for: "d1"
        )

        XCTAssertEqual(store.bundle(for: "d1")?.people, ["Alice"])
        XCTAssertFalse(store.loadFailed(for: "d1"))
    }

    func testRetryFailedLoadsClearsEveryFailureOnEngineReady() {
        let store = makeStore()
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "d1")
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "d2")

        store.retryFailedLoads()

        XCTAssertFalse(store.loadFailed(for: "d1"))
        XCTAssertFalse(store.loadFailed(for: "d2"))
    }

    func testNamesForEntityTypeMatchesTheParsedField() {
        let bundle = ArtifactEntityStore.parse([
            artifact("people", data: ["items": AnyCodable([["name": "Alice"]])]),
            artifact("keywords", data: ["keywords": AnyCodable(["war"])])
        ])
        // The per-column table cell reads through names(for:) — it must agree
        // with the multiLine row's per-field reads.
        XCTAssertEqual(bundle.names(for: "people"), ["Alice"])
        XCTAssertEqual(bundle.names(for: "keywords"), ["war"])
        XCTAssertEqual(bundle.names(for: "places"), [])
        XCTAssertEqual(bundle.names(for: "unknown"), [])
    }
}
