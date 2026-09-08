@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// spec: kg-tables — `kg.tables.claim.delete` (delete a claim FROM the table) +
/// `kg.tables.crud.in-place` (a delete drops that one row, never a wholesale reload).
///
/// The backend call (`EntityService.deleteClaim` per id) is I/O; the pure part is
/// WHICH rows leave the loaded array. `LibraryClaimsModel.removing(claimIds:from:)`
/// is that rule, pinned here off-main: a matched id is dropped, an unmatched id is a
/// no-op, and a claim with no id is never removed (absence is not a match).
struct ClaimsTableDeleteTests {

    private func claim(_ id: String?) -> Components.Schemas.KnowledgeClaim {
        Components.Schemas.KnowledgeClaim(id: id, text: "x")
    }

    @Test("removing a claim id drops that row and keeps the rest")
    func removesMatched() {
        let claims = [claim("a"), claim("b"), claim("c")]
        let kept = LibraryClaimsModel.removing(claimIds: ["b"], from: claims)
        #expect(kept.compactMap(\.id) == ["a", "c"])
    }

    @Test("removing several ids drops all of them")
    func removesMany() {
        let claims = [claim("a"), claim("b"), claim("c")]
        let kept = LibraryClaimsModel.removing(claimIds: ["a", "c"], from: claims)
        #expect(kept.compactMap(\.id) == ["b"])
    }

    @Test("an id not present is a no-op")
    func unmatchedIsNoOp() {
        let claims = [claim("a"), claim("b")]
        let kept = LibraryClaimsModel.removing(claimIds: ["zzz"], from: claims)
        #expect(kept.compactMap(\.id) == ["a", "b"])
    }

    @Test("a claim with no id is never removed")
    func nilIdSurvives() {
        let claims = [claim(nil), claim("a")]
        // Even an empty-string target must not sweep the nil-id row.
        let kept = LibraryClaimsModel.removing(claimIds: [""], from: claims)
        #expect(kept.count == 2)
    }
}
