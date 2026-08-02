@testable import Fichero
import XCTest

/// Claim writes go through `ClaimStore`, never straight to the services.
///
/// `ClaimStore` states this rule in its own doc comment — "a view never calls
/// `EntityService` / `KGCurationService` claim methods directly" — and for a
/// long time the app routed around it: six of its eight named write actions
/// had zero callers while the views needing exactly those operations called
/// the underlying services themselves.
///
/// That is a worse failure than two implementations nobody reconciled. The
/// reconciliation point existed, was written and was tested; it was simply not
/// used. The rule was enforced by nothing but the comment asserting it, and a
/// comment is not a constraint.
///
/// So this suite is the constraint. It reads source rather than behaviour
/// because what it guards IS a source-level property — which call a view makes
/// — and because the alternative is instantiating SwiftUI views with a live
/// library, which tests the harness more than the routing.
///
/// Why routing matters beyond tidiness: a store write reloads the claim scope,
/// so every claim surface reflects it (#1862). A direct service call updates
/// the server and leaves every other surface holding stale rows — which
/// presents as a sync bug, and gets investigated as one.
final class ClaimStoreRoutingTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // Models
            .deletingLastPathComponent()  // fichero-tests
            .deletingLastPathComponent()  // fichero
            .appendingPathComponent("fichero/fichero")
        return try String(contentsOf: root.appendingPathComponent(relativePath), encoding: .utf8)
    }

    // MARK: - Inspector bulk curation and merge

    func testInspectorBulkCurationRoutesThroughTheStore() throws {
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Actions.swift"
        )

        XCTAssertTrue(source.contains("claimStore.setCuration("))
        XCTAssertFalse(
            source.contains("kgCurationService.batchSetClaimCurationState("),
            "the store action wraps this exact call plus the scope reload"
        )
        XCTAssertFalse(source.contains("kgCurationService.batchCreateClaimRules("))
    }

    func testInspectorMergeRoutesThroughTheStore() throws {
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Actions.swift"
        )

        XCTAssertTrue(source.contains("claimStore.merge("))
        XCTAssertFalse(source.contains("kgCurationService.mergeClaims("))
    }

    /// `pruneTrivialClaims` is deliberately still a direct call: `ClaimStore`
    /// has no action for it, and adding one as part of a routing pass would be
    /// inventing a capability rather than connecting an existing one.
    ///
    /// This test exists so that stays a RECORDED decision. Without it, the next
    /// person sweeping for direct service calls finds one survivor and cannot
    /// tell whether it was considered or missed.
    func testPruneTrivialIsKnowinglyStillDirect() throws {
        let source = try Self.appSource(
            "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection+Actions.swift"
        )

        XCTAssertTrue(
            source.contains("kgCurationService.pruneTrivialClaims("),
            "if this moved to the store, delete this test and its note — do not "
                + "silently leave a test asserting the old shape"
        )
    }

    // MARK: - The review queue

    func testReviewQueueRoutesThroughTheStore() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimReviewQueueSheet.swift"
        )

        XCTAssertTrue(source.contains("claimStore.patch("))
        XCTAssertFalse(
            source.contains("entityService.patchClaim("),
            "this sheet used to edit a list that did not know it had changed"
        )
    }

    /// It also stops reaching for the global-library singleton.
    ///
    /// That was a live bug, not only a style point: the sheet resolved
    /// `LibraryManager.shared.globalLibrary` regardless of which window it was
    /// open in, so in a detached window on a second library it wrote curation
    /// states to the WRONG library. Taking the store from the environment makes
    /// it the window's store by construction.
    func testReviewQueueDoesNotReachForTheGlobalLibrary() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimReviewQueueSheet.swift"
        )

        XCTAssertFalse(source.contains("LibraryManager.shared.globalLibrary"))
        XCTAssertTrue(source.contains("@Environment(ClaimStore.self)"))
    }

    // MARK: - Heuristic link acceptance

    func testHeuristicAcceptRoutesThroughTheStore() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Claim/HeuristicReviewSheet.swift"
        )

        XCTAssertTrue(source.contains("claimStore.link("))
        XCTAssertFalse(source.contains("entityService.createClaimLink("))
        XCTAssertFalse(source.contains("LibraryManager.shared.globalLibrary"))
    }

    // MARK: - The rule, swept

    /// No view anywhere calls a claim-writing service method directly.
    ///
    /// A sweep rather than a list, because the failure this guards is a NEW
    /// view added later that copies the old shape — exactly how the six
    /// uncalled store actions came to be routed around in the first place.
    /// `pruneTrivialClaims` is excluded by name and by the recorded reason
    /// above.
    func testNoViewWritesClaimsThroughAServiceDirectly() throws {
        let viewsRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/fichero/Views")

        let banned = [
            "entityService.patchClaim(",
            "entityService.deleteClaim(",
            "entityService.createClaimLink(",
            "entityService.transitionClaim(",
            "entityService.batchTransitionClaims(",
            "kgCurationService.batchSetClaimCurationState(",
            "kgCurationService.mergeClaims(",
            "kgCurationService.unmergeClaims("
        ]

        let enumerator = FileManager.default.enumerator(
            at: viewsRoot, includingPropertiesForKeys: nil
        )
        var scanned = 0
        var offenders: [String] = []

        while let url = enumerator?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            guard let source = try? String(contentsOf: url, encoding: .utf8) else { continue }
            scanned += 1
            for call in banned where source.contains(call) {
                offenders.append("\(url.lastPathComponent): \(call)")
            }
        }

        // The sweep must know it swept something. Zero files scanned and zero
        // offenders print the same result, and the Views tree has hundreds.
        XCTAssertGreaterThan(
            scanned, 100,
            "scanned only \(scanned) files — the tree moved and this guard went blind"
        )
        XCTAssertEqual(
            offenders, [],
            "these views bypass ClaimStore; route them through the named action"
        )
    }
}
