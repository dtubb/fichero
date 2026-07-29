@testable import Fichero
import Foundation
import XCTest

/// Regression coverage for #4056: the Debug-external (UDS or HTTPS :8765)
/// readiness budget is 15s, not the original 5s. Under Debug the engine is
/// developer-run (`start_backend.sh`, not bundled — #3042) and can take longer
/// than 5s to bind the UDS socket / HTTPS listener and answer the authenticated
/// probe on a cold/contended machine, which surfaced a false "not ready" /
/// recovery prompt. These source-inspection tests pin the budget so a revert
/// to 5s (or an accidental tightening) fails here.
///
/// The Release/embedded budgets are intentionally NOT loosened —
/// `spawnAndAdoptEmbeddedEngine` keeps its 30s adopt-existing cap and its
/// child-bounded spawned wait (#3930). This test pins both edges.
final class EmbeddedBackendDebugReadinessBudgetTests: XCTestCase {

    private static func source(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - Debug-external readiness budget is 15s

    /// The debug-external adoption path (`adoptDebugExternalEngine`, the ONLY
    /// path that dials a developer-run engine over UDS or HTTPS :8765 in Debug)
    /// must wait 15s — not the original 5s. A regression that reverts the
    /// literal or drops the named constant fails here.
    func testDebugExternalReadinessBudgetIs15Seconds() throws {
        let source = try Self.source("Services/EmbeddedBackendService+Lifecycle.swift")

        // Named constant pins the value in one place; the call site references
        // it by name so a future tightening is a one-line review.
        XCTAssertTrue(
            source.contains("private let debugExternalReadinessTimeout: TimeInterval = 15"),
            "Debug-external readiness budget must be declared as debugExternalReadinessTimeout = 15 (#4056)"
        )

        // The adoption call site must use the named constant, not a raw literal,
        // so the budget can't drift between declaration and use.
        XCTAssertTrue(
            source.contains("waitForBackend(timeout: debugExternalReadinessTimeout)"),
            "adoptDebugExternalEngine must wait on debugExternalReadinessTimeout, not a raw literal"
        )

        // Forbidden: the original 5s literal must NOT survive in the
        // debug-external adoption block. A bare `timeout: 5` there is the
        // exact regression #4056 fixed. Scope to the
        // `adoptDebugExternalEngine` body so the configured-remote `timeout: 5`
        // (a DIFFERENT path) doesn't false-positive.
        let debugBlockStart = source.range(of: "func adoptDebugExternalEngine()")
        let debugBlockEnd = debugBlockStart.flatMap { start in
            source.range(of: "private func spawnAndAdoptEmbeddedEngine()", range: start.upperBound..<source.endIndex)
        }
        if let start = debugBlockStart, let end = debugBlockEnd {
            let debugBlock = source[start.lowerBound..<end.lowerBound]
            XCTAssertFalse(
                debugBlock.contains("waitForBackend(timeout: 5)"),
                "The debug-external readiness wait must not be 5s (#4056 raised it to 15s)"
            )
        } else {
            XCTFail("Could not locate adoptDebugExternalEngine / spawnAndAdoptEmbeddedEngine block boundaries for scoped check")
        }
    }

    // MARK: - Release/embedded budgets are NOT loosened

    /// The Release/embedded adopt-existing cap stays at 30s — #4056 raises ONLY
    /// the debug-external budget. If someone bumps the 30s along with the
    /// debug fix, this fails.
    func testReleaseEmbeddedAdoptExistingBudgetStaysAt30Seconds() throws {
        let source = try Self.source("Services/EmbeddedBackendService+Lifecycle.swift")

        XCTAssertTrue(
            source.contains("waitForBackend(timeout: 30)"),
            "Release/embedded adopt-existing budget must remain 30s (unchanged by #4056)"
        )
    }

    // MARK: - Debug budget is strictly larger than the release adopt-existing cap relation

    /// Sanity: the debug-external budget (15s) must be >= the preview/test inert
    /// budget (1.5s) and the configured-remote budget (5s), and the release
    /// adopt-existing cap (30s) must remain the largest clock-bound wait. This
    /// catches a future edit that inverts the budgets.
    func testBudgetOrderingIsConsistent() throws {
        let source = try Self.source("Services/EmbeddedBackendService+Lifecycle.swift")

        XCTAssertTrue(source.contains("waitForBackend(timeout: 1.5)"), "Inert preview/test budget must stay 1.5s")
        XCTAssertTrue(source.contains("waitForBackend(timeout: 5)"), "Configured-remote budget must stay 5s")
        XCTAssertTrue(source.contains("waitForBackend(timeout: 30)"), "Release adopt-existing budget must stay 30s")
        XCTAssertTrue(
            source.contains("debugExternalReadinessTimeout: TimeInterval = 15"),
            "Debug-external budget must stay 15s"
        )
    }
}