@testable import Fichero
import FicheroAPIClient
import XCTest

/// spec: kg-tables — `claim.create` (hand-author a claim FROM the table, wiring POST
/// /api/claims), `claim.create.source-optional-flagged` (a sourceless claim is marked a
/// lower-provenance working hypothesis), and `crud.cross-surface` (the capability reaches
/// the UX, not only backend/MCP/CLI).
///
/// Capability-AVAILABILITY test (Testing Constitution): pins that the claims table wires
/// the create path and that the create records HUMAN authorship + flags a sourceless
/// claim, so those rules can't be silently dropped. Reads the surfaces' source — the repo
/// idiom for "this capability is present in this surface".
final class ClaimsTableCreateTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testClaimsTableOffersManualCreateWiredToTheSheet() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Table/ClaimsLibraryContent.swift")
        XCTAssertTrue(source.contains("New Claim"),
                      "the claims table must offer a New Claim affordance")
        XCTAssertTrue(source.contains("showingCreateSheet"),
                      "the affordance must present the create sheet")
        XCTAssertTrue(source.contains("NewClaimSheet("),
                      "create must present NewClaimSheet")
    }

    func testCreateGoesThroughPostApiClaimsAsHuman() throws {
        let source = try Self.appSource("Services/EntityService+ClaimEntityCRUD.swift")
        XCTAssertTrue(source.contains("createClaimApiClaimsPost"),
                      "claim.create must POST /api/claims via the generated client")
        XCTAssertTrue(source.contains("createdBy = \"human\""),
                      "a hand-authored claim must be recorded as human authorship")
    }

    func testSourcelessClaimIsFlaggedNotSilent() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Claim/NewClaimSheet.swift"
        )
        XCTAssertTrue(source.contains("entityService.createClaim"),
                      "the sheet must create through EntityService.createClaim")
        XCTAssertTrue(source.lowercased().contains("working hypothesis"),
                      "a sourceless claim must be flagged as a working hypothesis, not silent")
    }

    func testClaimsTableOffersEditReusingTheExistingSVOEditor() throws {
        // Edit-from-table (spec `claim.edit`) completes claim CRUD; it REUSES the
        // existing EditClaimSheet (PATCH, edits S·V·O fields) rather than a new editor.
        let content = try Self.appSource("Views/Library/ViewModes/Table/ClaimsLibraryContent.swift")
        XCTAssertTrue(content.contains("claimToEdit"),
                      "the claims table must hold an edit target")
        XCTAssertTrue(content.contains("EditClaimSheet(claim:"),
                      "edit must reuse the existing EditClaimSheet")
        let tableView = try Self.appSource("Views/Library/ViewModes/Table/ClaimsTableView.swift")
        XCTAssertTrue(tableView.contains("Edit…"),
                      "the claim row menu must offer an Edit affordance")
    }
}
