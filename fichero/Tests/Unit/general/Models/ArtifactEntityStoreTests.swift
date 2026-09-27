@testable import Fichero
import FicheroAPIClient
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

    // MARK: - ChangeEventConsumer: artifact.updated revision + invalidation (#4890)
    //
    // spec: segment.overlay.refreshes-when-segmentation-finishes. Through the
    // REAL `apply(_ event: ChangeEvent)`, not a source scan — same construction
    // idiom as ObservableDomainStoreTests.makeEvent.

    private func makeChangeEvent(type: String, documentIds: [String], extra: [String: Any] = [:]) throws -> ChangeEvent {
        var payload: [String: Any] = ["type": type, "document_ids": documentIds, "actor": "workflow"]
        payload.merge(extra) { _, new in new }
        let data = try JSONSerialization.data(withJSONObject: payload)
        return try JSONDecoder().decode(ChangeEvent.self, from: data)
    }

    /// CHANGE 1 (team-lead ruling, 2026-09-19): the revision bump is NOT
    /// gated on a held bundle — a Preview pane can show doc-1 with no
    /// Inspector bundle held for it, and the overlay still needs to know.
    func testArtifactUpdatedBumpsRevisionForNamedDocumentOnlyRegardlessOfHeldBundle() throws {
        let store = makeStore()
        // Neither doc-1 nor doc-2 has a bundle or a failed read — nothing held.
        XCTAssertNil(store.bundle(for: "doc-1"))
        XCTAssertEqual(store.revision(for: "doc-1"), 0)

        store.apply(try makeChangeEvent(type: "artifact.updated", documentIds: ["doc-1"]))

        XCTAssertEqual(store.revision(for: "doc-1"), 1, "the named document's revision bumps even though nothing was held")
        XCTAssertEqual(store.revision(for: "doc-2"), 0, "an unrelated document's revision must not move")
    }

    /// The SEPARATE half of CHANGE 1: a held bundle for the named document IS
    /// invalidated; a held bundle for an unrelated document is not.
    /// `invalidate(_:)`'s synchronous half — clearing `failedDocumentIds` — is
    /// the same observable precedent `testInvalidateClearsTheFailedMarkSoTheRetryDecides`
    /// above uses; the async refetch itself is left to the integration build.
    func testArtifactUpdatedInvalidatesOnlyHeldDocumentsNamedByTheEvent() throws {
        let store = makeStore()
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "doc-1")
        store.apply(fetchOutcome: .failure(TestTransportError()), for: "doc-2")
        XCTAssertTrue(store.loadFailed(for: "doc-1"))
        XCTAssertTrue(store.loadFailed(for: "doc-2"))

        store.apply(try makeChangeEvent(type: "artifact.updated", documentIds: ["doc-1"]))

        XCTAssertFalse(store.loadFailed(for: "doc-1"), "doc-1 is named by the event and held (failed) — invalidated")
        XCTAssertTrue(store.loadFailed(for: "doc-2"), "doc-2 is held but NOT named by the event — untouched")
    }

    /// A non-"artifact" domain event must not move anything — defensive, since
    /// `apply` is also reachable directly (as here), not only through
    /// `LibraryChangeStream.route(_:)`'s upstream domain filter.
    func testNonArtifactEventBumpsNothing() throws {
        let store = makeStore()

        store.apply(try makeChangeEvent(type: "document.updated", documentIds: ["doc-1"]))

        XCTAssertEqual(store.revision(for: "doc-1"), 0)
    }

    // MARK: - created and updated are ONE signal (#4890)
    //
    // The engine emits BOTH names for "this page's artifacts changed", and which
    // one you get is a matter of which code path wrote the artifact:
    //
    //   `artifact.updated` — the run boundary (`completion.finalize_run_documents`)
    //                        and the on-demand alignment route
    //                        (`POST /api/artifacts/{id}/align-transcript`).
    //   `artifact.created` — six workflow tools that emit mid-run through
    //                        `emit_workflow_artifact_changes`, whose `change_type`
    //                        defaults to "created": extract_all, extractors,
    //                        import_artifacts, catalogue, cleanup, date_extract.
    //
    // They are one signal because dispatch is by DOMAIN: `ChangeEvent.domain` is
    // the prefix before the dot, `LibraryChangeStream` delivers by that domain,
    // and `apply` guards on `event.domain == "artifact"` with no verb filter.
    //
    // That is an architectural property and, before these two tests, it was
    // pinned by nothing. A tidy-up adding `guard event.type == "artifact.updated"`
    // would silence six emitters — and silently, because the store would keep
    // working perfectly for the two paths the existing tests cover. These tests
    // make the property a stated contract instead of an accident.

    /// `artifact.created` must bump the revision exactly as `artifact.updated` does.
    /// If this fails, six engine tools have gone silent and no other test notices.
    func testArtifactCreatedBumpsTheRevisionToo() throws {
        let store = makeStore()

        store.apply(try makeChangeEvent(type: "artifact.created", documentIds: ["doc-1"]))

        XCTAssertEqual(
            store.revision(for: "doc-1"), 1,
            "artifact.created is the name six workflow tools emit; the overlay must react to it"
        )
    }

    /// The two names are interchangeable for this store: same document, one of
    /// each, two bumps. Asserted as a PAIR rather than as two separate cases,
    /// because the claim is about their equivalence and not about either alone.
    func testCreatedAndUpdatedAreTheSameSignalForTheSameDocument() throws {
        let store = makeStore()

        store.apply(try makeChangeEvent(type: "artifact.created", documentIds: ["doc-1"]))
        store.apply(try makeChangeEvent(type: "artifact.updated", documentIds: ["doc-1"]))

        XCTAssertEqual(
            store.revision(for: "doc-1"), 2,
            "each artifact.* event is one bump regardless of its verb — a loader keyed on "
            + "revision(for:) re-fires for both"
        )
    }

    /// The guard that must NOT be widened by accident while doing the above: the
    /// domain still decides. `document.created` is a real event name, and it is
    /// the near miss most likely to be let through by a looser check.
    func testAnotherDomainsCreatedEventStillBumpsNothing() throws {
        let store = makeStore()

        store.apply(try makeChangeEvent(type: "document.created", documentIds: ["doc-1"]))

        XCTAssertEqual(
            store.revision(for: "doc-1"), 0,
            "the domain decides, not the verb — document.created is not an artifact event"
        )
    }

    /// Proves the `artifact_ids` key (the engine's actual payload shape,
    /// `completion.py`'s `emit_change(..., artifact_ids=..., document_ids=...)`)
    /// decodes alongside `document_ids` and neither is harmed by the other's
    /// presence. UPDATED (source-model slice 2, #4920,
    /// `source.events.segment-ids`): `ChangeEvent` now HAS a field for
    /// `artifact_ids` — it used to be an unmapped key `Decodable` silently
    /// ignored; this test's own premise ("no field for it") predates that
    /// change and is corrected here rather than left stale.
    func testArtifactIdsKeyDecodesAlongsideDocumentIds() throws {
        let event = try makeChangeEvent(
            type: "artifact.updated",
            documentIds: ["doc-1"],
            extra: ["artifact_ids": ["art-1", "art-2"], "run_id": "run-9"]
        )
        XCTAssertEqual(event.documentIds, ["doc-1"])
        XCTAssertEqual(event.artifactIds, ["art-1", "art-2"])
        XCTAssertEqual(event.runId, "run-9")

        let store = makeStore()
        store.apply(event)
        XCTAssertEqual(store.revision(for: "doc-1"), 1)
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
