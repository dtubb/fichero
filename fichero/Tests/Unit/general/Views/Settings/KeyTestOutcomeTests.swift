@testable import Fichero
import SwiftUI
import XCTest

/// #4816 (Swift half): `ConnectionTestResponse.success` alone used to decide
/// the green-check/red-x icon — but a successful round-trip does not prove
/// the KEY itself was verified. Several providers (OpenRouter among them)
/// accepted any non-empty key at the connect step and still showed green.
/// The engine now reports `verified: Bool?` (regenerated client, 8dae9c0c2);
/// `KeyTestOutcome.from(success:verified:)` is the pure derivation that turns
/// that pair into the three states the UI actually needs.
final class KeyTestOutcomeTests: XCTestCase {

    // MARK: - Exhaustive over every (success, verified) combination

    func testSuccessAndVerifiedTrueIsVerified() {
        XCTAssertEqual(KeyTestOutcome.from(success: true, verified: true), .verified)
    }

    func testSuccessAndVerifiedFalseIsSavedNotVerified() {
        XCTAssertEqual(KeyTestOutcome.from(success: true, verified: false), .savedNotVerified)
    }

    func testSuccessAndVerifiedNilIsSavedNotVerified() {
        // The regenerated field is nullable — an engine that has not been
        // taught to probe a given provider yet reports no opinion at all.
        // That is NOT the same as a positive verification.
        XCTAssertEqual(KeyTestOutcome.from(success: true, verified: nil), .savedNotVerified)
    }

    func testFailureAndVerifiedTrueIsStillFailed() {
        // success is the gate — a claimed "verified: true" cannot rescue a
        // round-trip that failed outright.
        XCTAssertEqual(KeyTestOutcome.from(success: false, verified: true), .failed)
    }

    func testFailureAndVerifiedFalseIsFailed() {
        XCTAssertEqual(KeyTestOutcome.from(success: false, verified: false), .failed)
    }

    func testFailureAndVerifiedNilIsFailed() {
        XCTAssertEqual(KeyTestOutcome.from(success: false, verified: nil), .failed)
    }

    // MARK: - The neutral state is never green

    func testSavedNotVerifiedTintIsNeverGreen() {
        XCTAssertEqual(KeyTestOutcome.savedNotVerified.tint, .secondary)
    }

    func testVerifiedTintIsGreenAndFailedTintIsRed() {
        XCTAssertEqual(KeyTestOutcome.verified.tint, .green)
        XCTAssertEqual(KeyTestOutcome.failed.tint, .red)
    }

    func testEachOutcomeHasADistinctIcon() {
        let icons = Set([
            KeyTestOutcome.verified.systemImage,
            KeyTestOutcome.failed.systemImage,
            KeyTestOutcome.savedNotVerified.systemImage
        ])
        XCTAssertEqual(icons.count, 3, "three outcomes must not collapse back onto the same icon")
    }

    // MARK: - Source-scan: the view must not key its icon on `result.success` alone

    private static func appSource(_ relativePath: String) throws -> String {
        try AppSource.text(relativePath)
    }

    func testProviderDetailViewDoesNotKeyTheTestIconOnSuccessAlone() throws {
        let source = try Self.appSource(
            "Views/Settings/AI/AIProviders/ProvidersView+ProviderDetailView.swift"
        )

        // The regression this whole delivery fixes: a ternary that only ever
        // looks at `result.success` for the icon/color. If this string is
        // back, `verified` has been dropped from the render path again.
        XCTAssertFalse(
            source.contains(#"result.success ? "checkmark.circle.fill" : "xmark.circle.fill""#),
            "the connection-test icon must not go back to a binary success-only ternary (#4816)"
        )
        XCTAssertTrue(
            source.contains("KeyTestOutcome.from(success: result.success, verified: result.verified)"),
            "the connection-test icon must derive from KeyTestOutcome, not result.success alone"
        )
    }
}
