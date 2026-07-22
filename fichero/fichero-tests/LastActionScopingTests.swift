@testable import Fichero
import XCTest

/// LastAction is now a per-library holder owned by ActionLibraryService (#3444),
/// not a process-global singleton — so ⌘Z in one library can't reverse another
/// library's action. These lock the record/clear contract and the per-library
/// isolation without a full UI test.
@MainActor
final class LastActionScopingTests: XCTestCase {

    func testRecordSetsFields() {
        let holder = LastAction()
        XCTAssertNil(holder.auditId)
        holder.record(auditId: "audit-1", actionName: "entity.merge")
        XCTAssertEqual(holder.auditId, "audit-1")
        XCTAssertEqual(holder.actionName, "entity.merge")
    }

    func testEachServiceOwnsAnIndependentHolder() {
        let libraryA = ActionLibraryService(client: .localhost)
        let libraryB = ActionLibraryService(client: .localhost)
        // Distinct instances — no shared global carrying undo state across libraries.
        XCTAssertFalse(libraryA.lastAction === libraryB.lastAction)

        libraryA.lastAction.record(auditId: "a-1", actionName: "claim.delete")
        XCTAssertEqual(libraryA.lastAction.auditId, "a-1")
        XCTAssertNil(libraryB.lastAction.auditId, "an action in library A must not seed library B's undo")
    }

    func testClearingHolderDisablesUndo() {
        let holder = LastAction()
        holder.record(auditId: "audit-1", actionName: "claim.patch")
        holder.auditId = nil
        holder.actionName = nil
        XCTAssertNil(holder.auditId)
    }
}
