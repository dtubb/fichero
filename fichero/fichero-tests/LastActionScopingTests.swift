@testable import Fichero
import FicheroAPIClient
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
        // Explicit client construction — FicheroClient.localhost was removed
        // (ee20b94fd, #4051) but this file kept calling it, breaking the whole
        // FicheroTests bundle at compile. Matches sibling tests' pattern.
        let libraryA = ActionLibraryService(client: FicheroClient(libraryPath: nil))
        let libraryB = ActionLibraryService(client: FicheroClient(libraryPath: nil))
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
