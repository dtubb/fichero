@testable import Fichero
import XCTest

/// Move, copy and alias must DELIVER in the store's own model (#4473 applied
/// to the library).
///
/// The Swift side had no outcome test for any of the three operations Daniel
/// named. What existed was `source.contains("documentStore.moveDocument(...)")`
/// — a check that a line of code is present, which goes green over a move that
/// reparents nothing.
///
/// The server proves the row moved: 18 outcome tests re-read `parent_id`. What
/// nothing proved is that the CLIENT stops showing the document where it used
/// to be. `DocumentStore.updateLocal` is the code that does that, its own
/// comment says *"or the grid keeps showing a document that now lives
/// somewhere else"* — and `updateLocal` appeared in no test in this suite.
///
/// That is the shape of the live report *"move in sidebars copies"*: a move
/// that leaves the old copy on screen is indistinguishable from a copy, and
/// every server test would still pass.
///
/// So these drive the store directly and assert on its state afterwards. No
/// GUI, no network — `updateLocal` is pure bookkeeping over `collections`,
/// `currentDocuments` and `childrenCache`, which is exactly the part that was
/// never checked.
@MainActor
final class DocumentStoreOperationOutcomeTests: XCTestCase {

    private func makeStore() -> DocumentStore {
        DocumentStore(apiClient: APIClient())
    }

    private func doc(
        _ id: String,
        parent: String? = nil,
        name: String? = nil,
        nodeKind: String? = nil,
        aliasTargetId: String? = nil
    ) -> Document {
        Document(
            id: id,
            parentId: parent,
            docType: .file,
            fileType: nil,
            name: name ?? id,
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            sortOrder: 0,
            nodeKind: nodeKind,
            aliasTargetId: aliasTargetId,
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
    }

    /// Every bucket the store holds a document in, so "did it move or did it
    /// copy" can be asked as one number.
    private func placements(of id: String, in store: DocumentStore) -> Int {
        var count = store.collections.filter { $0.id == id }.count
        count += store.currentDocuments.filter { $0.id == id }.count
        for (_, bucket) in store.childrenCache {
            count += bucket.filter { $0.id == id }.count
        }
        return count
    }

    // MARK: - ALIAS — two references, one document

    /// An alias's whole point is that two things are one thing. If it silently
    /// became a copy it would look correct in every screenshot and be wrong
    /// forever, so this is the first thing asserted.
    func testAnAliasAndItsTargetAreTwoRowsPointingAtOneDocument() {
        let target = doc("target", parent: "folderA", name: "Diary")
        let alias = doc("alias-1", parent: "folderB", name: "Diary alias",
                        nodeKind: "alias", aliasTargetId: "target")

        XCTAssertNotEqual(alias.id, target.id, "an alias is its own row")
        XCTAssertEqual(alias.aliasTargetId, target.id, "and it points at the target")
        XCTAssertTrue(alias.isAlias)
        XCTAssertFalse(target.isAlias, "the target is not an alias of itself")
    }

    /// The copy-detection assertion. A copy would carry the target's CONTENT;
    /// an alias carries only a reference. `page_content is None` is what the
    /// server's own alias test checks, and the client model must agree.
    func testAnAliasCarriesNoContentOfItsOwn() {
        let alias = doc("alias-1", parent: "folderB", nodeKind: "alias", aliasTargetId: "target")

        XCTAssertNil(alias.pageContent, "content lives in the target; an alias holding a copy of it IS a copy")
    }

    /// Moving the TARGET must not move, duplicate or orphan the alias. The
    /// alias's own `parentId` is where the user filed the reference, and it is
    /// unrelated to where the target lives.
    func testMovingTheTargetLeavesTheAliasWhereTheUserPutIt() {
        let store = makeStore()
        let target = doc("target", parent: "folderA")
        let alias = doc("alias-1", parent: "folderB", nodeKind: "alias", aliasTargetId: "target")
        store.childrenCache = ["folderA": [target], "folderB": [alias]]

        store.updateLocal(doc("target", parent: "folderC"))

        XCTAssertEqual(store.childrenCache["folderB"]?.map(\.id), ["alias-1"],
                       "the alias must not follow its target")
        XCTAssertEqual(store.childrenCache["folderB"]?.first?.aliasTargetId, "target",
                       "and it must still point at it")
        XCTAssertEqual(placements(of: "alias-1", in: store), 1)
    }

    /// And the reverse: re-filing the alias must not disturb the target.
    func testMovingTheAliasLeavesTheTargetAlone() {
        let store = makeStore()
        store.childrenCache = [
            "folderA": [doc("target", parent: "folderA")],
            "folderB": [doc("alias-1", parent: "folderB", nodeKind: "alias", aliasTargetId: "target")],
            "folderC": []
        ]

        store.updateLocal(doc("alias-1", parent: "folderC", nodeKind: "alias", aliasTargetId: "target"))

        XCTAssertEqual(store.childrenCache["folderA"]?.map(\.id), ["target"])
        XCTAssertEqual(store.childrenCache["folderC"]?.map(\.id), ["alias-1"])
        XCTAssertEqual(placements(of: "target", in: store), 1)
    }

    // MARK: - MOVE — the reported bug's shape

    /// **The assertion the live report needed.** After a move the document
    /// exists in exactly ONE place in the store. Two placements IS a copy, as
    /// far as anyone looking at the app can tell.
    func testAMoveLeavesTheDocumentInExactlyOnePlace() {
        let store = makeStore()
        store.childrenCache = ["folderA": [doc("d1", parent: "folderA")], "folderB": []]

        store.updateLocal(doc("d1", parent: "folderB"))

        XCTAssertEqual(placements(of: "d1", in: store), 1,
                       "a document in two buckets is a move that renders as a copy")
        XCTAssertEqual(store.childrenCache["folderA"]?.map(\.id), [])
        XCTAssertEqual(store.childrenCache["folderB"]?.map(\.id), ["d1"])
    }

    /// The grid case named in `updateLocal`'s own comment: viewing the source
    /// folder while a document moves out of it.
    func testMovingOutOfTheVIEWEDFolderRemovesItFromTheGrid() {
        let store = makeStore()
        store.selectedCollection = doc("folderA", parent: nil)
        store.currentDocuments = [doc("d1", parent: "folderA"), doc("d2", parent: "folderA")]

        store.updateLocal(doc("d1", parent: "folderB"))

        XCTAssertEqual(store.currentDocuments.map(\.id), ["d2"],
                       "the grid must not keep showing a document that now lives elsewhere")
    }

    /// ...and the same document arriving in the viewed folder is replaced in
    /// place rather than removed. Both halves matter: a rule that only removes
    /// would empty the grid on every update.
    func testAnUpdateWITHINTheViewedFolderReplacesInPlace() {
        let store = makeStore()
        store.selectedCollection = doc("folderA", parent: nil)
        store.currentDocuments = [doc("d1", parent: "folderA", name: "Old")]

        store.updateLocal(doc("d1", parent: "folderA", name: "New"))

        XCTAssertEqual(store.currentDocuments.map(\.name), ["New"])
        XCTAssertEqual(store.currentDocuments.count, 1, "replaced, not appended")
    }

    /// Moving to root — `parentId == nil` — is the case a naive equality check
    /// gets wrong, because nil matches "no viewed folder" by accident.
    func testMovingToRootRemovesItFromItsOldParentBucket() {
        let store = makeStore()
        store.childrenCache = ["folderA": [doc("d1", parent: "folderA")]]
        store.collections = [doc("d1", parent: "folderA")]

        store.updateLocal(doc("d1", parent: nil))

        XCTAssertEqual(store.childrenCache["folderA"]?.map(\.id), [])
        let rootRow = try? XCTUnwrap(store.collections.first { $0.id == "d1" })
        XCTAssertNotNil(rootRow, "the row must survive the move to root")
        XCTAssertNil(rootRow?.parentId, "the root listing must reflect the new parent")
    }

    /// A document already in the destination bucket must not be duplicated by
    /// an update that re-confirms where it is — the idempotence case, which is
    /// what a retried or echoed change-stream event looks like.
    func testReapplyingTheSameMoveDoesNotDuplicate() {
        let store = makeStore()
        store.childrenCache = ["folderA": [], "folderB": [doc("d1", parent: "folderB")]]

        store.updateLocal(doc("d1", parent: "folderB"))
        store.updateLocal(doc("d1", parent: "folderB"))

        XCTAssertEqual(store.childrenCache["folderB"]?.count, 1)
        XCTAssertEqual(placements(of: "d1", in: store), 1)
    }

    /// The selection must follow the document, not the position. Selecting a
    /// folder and then moving it left the store holding a stale copy with the
    /// old parent, which is how a breadcrumb ends up pointing at the wrong
    /// place.
    func testMovingTheSELECTEDDocumentUpdatesTheSelection() {
        let store = makeStore()
        store.selectedDocument = doc("d1", parent: "folderA")
        store.selectedCollection = doc("folderX", parent: "folderA")

        store.updateLocal(doc("d1", parent: "folderB"))
        store.updateLocal(doc("folderX", parent: "folderB"))

        XCTAssertEqual(store.selectedDocument?.parentId, "folderB")
        XCTAssertEqual(store.selectedCollection?.parentId, "folderB")
    }

    // MARK: - COPY — both exist, and they are distinct

    /// A duplicate is a genuinely new row. The two must not collapse onto one
    /// identity anywhere in the store, or the copy silently overwrites its
    /// original in the cache.
    func testACopyAndItsOriginalAreDistinctRowsInTheSameBucket() {
        let store = makeStore()
        store.childrenCache = ["folderA": [doc("d1", parent: "folderA", name: "Paper")]]

        store.updateLocal(doc("d1-copy", parent: "folderA", name: "Paper copy"))

        let bucket = store.childrenCache["folderA"] ?? []
        XCTAssertEqual(Set(bucket.map(\.id)), ["d1", "d1-copy"], "both exist")
        XCTAssertEqual(bucket.count, 2)
        XCTAssertNotEqual(bucket[0].name, bucket[1].name, "and they are distinguishable")
    }

    // MARK: - The helper is not vacuous

    /// `placements(of:)` is doing the work in the assertions above, so it has
    /// to be shown to count more than one when there IS more than one —
    /// otherwise every "exactly one place" test passes by counting nothing.
    func testThePlacementCounterCanActuallySeeADuplicate() {
        let store = makeStore()
        store.childrenCache = ["folderA": [doc("d1", parent: "folderA")],
                               "folderB": [doc("d1", parent: "folderB")]]

        XCTAssertEqual(placements(of: "d1", in: store), 2,
                       "if this reads 1, every move test above is vacuous")
    }
}

/// The optimistic reorder must agree with itself across every container
/// (#4473 sweep).
///
/// `reorderChildrenOptimistically` is the other mutation that touches all
/// three of the store's containers — `collections`, `currentDocuments` and
/// every `childrenCache` bucket — and it had no test at all.
///
/// It is not cosmetic. `SidebarItemBuilder.childOrder` reads `sortOrder` to
/// produce the visible order on the next render, which is what satisfies
/// SwiftUI's `.onMove` contract that the data source reflects the move
/// synchronously. If the containers disagree about a document's `sortOrder`,
/// the sidebar and the grid draw the same siblings in different orders — and
/// nothing would fail, because both are internally consistent.
///
/// So the assertion here is AGREEMENT, not correctness of any single value.
@MainActor
final class DocumentStoreReorderOutcomeTests: XCTestCase {

    private func doc(_ id: String, parent: String? = nil, sortOrder: Int = 0) -> Document {
        Document(
            id: id, parentId: parent, docType: .file, fileType: nil, name: id,
            path: nil, sequence: nil, bbox: nil, status: .completed,
            metadata: [:], pageContent: nil, sortOrder: sortOrder,
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
    }

    /// Every sortOrder the store holds for one document, across all containers.
    private func recordedOrders(of id: String, in store: DocumentStore) -> Set<Int> {
        var orders = Set(store.collections.filter { $0.id == id }.map(\.sortOrder))
        orders.formUnion(store.currentDocuments.filter { $0.id == id }.map(\.sortOrder))
        for (_, bucket) in store.childrenCache {
            orders.formUnion(bucket.filter { $0.id == id }.map(\.sortOrder))
        }
        return orders
    }

    /// **The both-buckets question for this mutation.** A document living in
    /// the grid AND in a cache bucket must come out of a reorder with ONE
    /// value, or the two surfaces order the same siblings differently and
    /// neither looks broken on its own.
    func testEveryContainerAgreesOnTheNewSortOrder() {
        let store = DocumentStore(apiClient: APIClient())
        store.currentDocuments = [doc("a", parent: "f", sortOrder: 9), doc("b", parent: "f", sortOrder: 9)]
        store.childrenCache = ["f": [doc("a", parent: "f", sortOrder: 9), doc("b", parent: "f", sortOrder: 9)]]
        store.collections = [doc("a", parent: "f", sortOrder: 9)]

        store.reorderChildrenOptimistically(orderedIds: ["b", "a"])

        XCTAssertEqual(recordedOrders(of: "b", in: store), [0], "b is first, everywhere")
        XCTAssertEqual(recordedOrders(of: "a", in: store), [1], "a is second, everywhere")
    }

    /// Positions come from the index in `orderedIds`, so a reorder of three
    /// produces 0/1/2 rather than preserved-but-shuffled old values.
    func testPositionsAreTheIndexInTheRequestedOrder() {
        let store = DocumentStore(apiClient: APIClient())
        store.childrenCache = ["f": [doc("x", parent: "f", sortOrder: 5),
                                     doc("y", parent: "f", sortOrder: 3),
                                     doc("z", parent: "f", sortOrder: 8)]]

        store.reorderChildrenOptimistically(orderedIds: ["z", "x", "y"])

        let bucket = store.childrenCache["f"] ?? []
        XCTAssertEqual(bucket.first { $0.id == "z" }?.sortOrder, 0)
        XCTAssertEqual(bucket.first { $0.id == "x" }?.sortOrder, 1)
        XCTAssertEqual(bucket.first { $0.id == "y" }?.sortOrder, 2)
    }

    /// A sibling not named in the reorder must keep its value. Renumbering
    /// everything in the bucket would silently reorder rows the user never
    /// touched — and with a comparator reading these, that IS the visible
    /// order.
    func testDocumentsOutsideTheRequestKeepTheirOrder() {
        let store = DocumentStore(apiClient: APIClient())
        store.childrenCache = ["f": [doc("a", parent: "f", sortOrder: 0),
                                     doc("untouched", parent: "f", sortOrder: 77)]]

        store.reorderChildrenOptimistically(orderedIds: ["a"])

        XCTAssertEqual(
            store.childrenCache["f"]?.first { $0.id == "untouched" }?.sortOrder, 77,
            "a reorder of one sibling must not renumber the others"
        )
    }

    /// A document in a DIFFERENT folder that happens to be named in the list
    /// still gets its position — the request is by id, and the store does not
    /// second-guess which bucket the caller meant. Pinned so that if this ever
    /// becomes parent-scoped it is a decision rather than a surprise.
    func testTheRequestIsByIdAcrossBuckets() {
        let store = DocumentStore(apiClient: APIClient())
        store.childrenCache = ["f": [doc("a", parent: "f", sortOrder: 9)],
                               "g": [doc("a", parent: "g", sortOrder: 9)]]

        store.reorderChildrenOptimistically(orderedIds: ["a"])

        XCTAssertEqual(recordedOrders(of: "a", in: store), [0])
    }

    /// The counter must be able to SEE a disagreement, or every agreement
    /// assertion above passes by measuring nothing.
    func testTheOrderCounterCanSeeADisagreement() {
        let store = DocumentStore(apiClient: APIClient())
        store.currentDocuments = [doc("a", parent: "f", sortOrder: 1)]
        store.childrenCache = ["f": [doc("a", parent: "f", sortOrder: 2)]]

        XCTAssertEqual(recordedOrders(of: "a", in: store), [1, 2],
                       "if this reads a single value, the agreement tests are vacuous")
    }
}
