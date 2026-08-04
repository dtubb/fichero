@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// `EntityStore` holds three containers for the same domain, and removing an
/// entity has to reach all three (#4489).
///
/// ## The defect class, not the instance
///
/// The three containers cannot be collapsed into one. `libraryClaimCounts`
/// comes from its own endpoint and `KnowledgeEntity` carries no claim count, so
/// it is not derivable from `libraryEntities` the way the deleted legacy
/// `entities` mirror was derivable from `entitiesByDocumentId`. What could be
/// collapsed was the number of WRITERS: three call sites each independently
/// responsible for remembering all three containers, and only one of them
/// remembering. `merge` forgot `libraryClaimCounts` (③) and the change-stream
/// `deleted` branch forgot everything (②).
///
/// ## Why these tests are shaped this way
///
/// Every test below removes ONE id from a store seeded with TWO, and asserts
/// both halves: the target is gone from all three containers, and the bystander
/// survives in all three. A test that only asserted the first half would pass
/// against a store that simply cleared everything, which is a worse bug than
/// the one being fixed.
///
/// The per-container assertions are deliberately separate. A single
/// "everything is consistent" assertion would report the same failure whichever
/// container drifted, and the whole point is that ONE of three was forgotten.
@MainActor
final class EntityStorePartialReconciliationTests: XCTestCase {

    // MARK: - Fixtures

    private func makeStore() -> EntityStore {
        // No request is made by any test here — the seam under test is
        // synchronous — but the store needs its services to exist. An ephemeral
        // session with no protocol classes cannot reach the network by accident.
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = []
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
        return EntityStore(
            entityService: EntityService(ficheroClient: client),
            kgCurationService: KGCurationService(ficheroClient: client),
            libraryPath: "/tmp/test.fichero"
        )
    }

    private func entity(_ id: String) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(
            id: id,
            canonicalName: id,
            entityType: .person,
            aliases: nil,
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil
        )
    }

    /// A store holding "doomed" and "keeper" in all three containers, with
    /// `doomed` present in TWO document buckets — a single-bucket fixture would
    /// pass against code that only pruned the current scope.
    private func seededStore() -> EntityStore {
        let store = makeStore()
        store.libraryEntities = [entity("doomed"), entity("keeper")]
        store.libraryClaimCounts = ["doomed": 3, "keeper": 7]
        store.entitiesByDocumentId = [
            "doc-1": [entity("doomed"), entity("keeper")],
            "doc-2": [entity("doomed")]
        ]
        return store
    }

    private func ids(_ entities: [Components.Schemas.KnowledgeEntity]) -> [String] {
        entities.compactMap(\.id)
    }

    // MARK: - The seam removes from all three containers

    func testRemovalPrunesTheLibraryList() {
        let store = seededStore()
        store.removeEntitiesEverywhere(ids: ["doomed"])

        XCTAssertEqual(ids(store.libraryEntities), ["keeper"])
    }

    /// The container `merge` forgot (#4489 ③). An absorbed entity kept its
    /// claim-count entry forever.
    func testRemovalPrunesTheClaimCounts() {
        let store = seededStore()
        store.removeEntitiesEverywhere(ids: ["doomed"])

        XCTAssertNil(
            store.libraryClaimCounts["doomed"],
            "a removed entity must not keep a claim count — this is the entry merge left behind"
        )
        XCTAssertEqual(store.libraryClaimCounts["keeper"], 7, "and the survivor's count is untouched")
    }

    /// Every document bucket, not only the one on screen.
    func testRemovalPrunesEveryDocumentBucketNotJustTheCurrentOne() {
        let store = seededStore()
        store.removeEntitiesEverywhere(ids: ["doomed"])

        XCTAssertEqual(ids(store.entitiesByDocumentId["doc-1"] ?? []), ["keeper"])
        XCTAssertEqual(
            ids(store.entitiesByDocumentId["doc-2"] ?? []), [],
            "a bucket the user is not looking at is still stale state that will be shown later"
        )
    }

    /// The control. Without this, "remove everything" passes every test above.
    func testAnUnrelatedEntitySurvivesInAllThreeContainers() {
        let store = seededStore()
        store.removeEntitiesEverywhere(ids: ["doomed"])

        XCTAssertTrue(ids(store.libraryEntities).contains("keeper"))
        XCTAssertNotNil(store.libraryClaimCounts["keeper"])
        XCTAssertTrue(ids(store.entitiesByDocumentId["doc-1"] ?? []).contains("keeper"))
    }

    /// An event carrying no ids must not be read as "remove all".
    func testAnEmptyRemovalIsANoOp() {
        let store = seededStore()
        store.removeEntitiesEverywhere(ids: [])

        XCTAssertEqual(store.libraryEntities.count, 2)
        XCTAssertEqual(store.libraryClaimCounts.count, 2)
        XCTAssertEqual(store.entitiesByDocumentId["doc-1"]?.count, 2)
    }

    // MARK: - The push path agrees with the local path (#4489 ②)

    private func deletedEvent(entityIds: [String]) throws -> ChangeEvent {
        // Built by joining rather than interpolating the array: interpolating
        // `[String]` emits Swift's `description`, which escapes the quotes and
        // produces JSON that does not decode.
        let idList = entityIds.map { "\"\($0)\"" }.joined(separator: ", ")
        let json = """
        {
          "type": "entity.deleted",
          "entity_ids": [\(idList)],
          "claim_ids": [],
          "document_ids": [],
          "citation_ids": [],
          "reference_ids": [],
          "actor": "someone-else"
        }
        """
        return try JSONDecoder().decode(ChangeEvent.self, from: Data(json.utf8))
    }

    /// An entity deleted in another window used to survive in all three
    /// containers here, while the LOCAL delete pruned all three. Two branches of
    /// one capability, one of them complete.
    func testAPushedDeleteRemovesTheEntityEverywhere() throws {
        let store = seededStore()
        let event = try deletedEvent(entityIds: ["doomed"])
        store.apply(event)

        XCTAssertFalse(ids(store.libraryEntities).contains("doomed"))
        XCTAssertNil(store.libraryClaimCounts["doomed"])
        XCTAssertFalse(ids(store.entitiesByDocumentId["doc-1"] ?? []).contains("doomed"))
        XCTAssertFalse(ids(store.entitiesByDocumentId["doc-2"] ?? []).contains("doomed"))
    }

    /// The partial case that matters: a delete event naming an entity this
    /// store has never seen must not disturb what it holds.
    func testAPushedDeleteForAnUnknownEntityChangesNothing() throws {
        let store = seededStore()
        let event = try deletedEvent(entityIds: ["never-heard-of-it"])
        store.apply(event)

        XCTAssertEqual(store.libraryEntities.count, 2)
        XCTAssertEqual(store.libraryClaimCounts.count, 2)
    }

    /// A `deleted` event with an empty id list reaches the same guard as a local
    /// empty delete rather than clearing the store.
    func testAPushedDeleteWithNoIdsIsANoOp() throws {
        let store = seededStore()
        let event = try deletedEvent(entityIds: [])
        store.apply(event)

        XCTAssertEqual(store.libraryEntities.count, 2)
        XCTAssertEqual(store.entitiesByDocumentId["doc-2"]?.count, 1)
    }

    // MARK: - reload() must not invent a library scope (#4489 ④)

    /// `reload()` now refreshes the library containers too, but only if they
    /// were ever loaded. This flag is what makes that decidable: an
    /// inspector-only session has an empty `libraryEntities` and a nil
    /// `lastLibraryQuery`, which are also what a loaded-but-empty library looks
    /// like. Asserting the flag starts false is what stops a resync from
    /// issuing a library-wide query nobody asked for.
    func testAFreshStoreHasNotLoadedTheLibraryScope() {
        XCTAssertFalse(makeStore().didLoadLibraryScope)
    }
}
