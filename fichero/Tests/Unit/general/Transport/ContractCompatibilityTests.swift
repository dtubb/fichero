import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// #5047 — `contract.runtime-compatibility`, client half.
///
/// Spec: `docs/contributor_manual/specs/harness/version-and-contract-integrity.md`.
/// A mismatch REFUSES a remote connection and names both versions (design ruling 1).
///
/// These pin the DECISION, which is the part that can be wrong in both directions:
/// a false positive refuses every remote connection, a false negative allows a
/// connection whose bodies will fail to decode later for no visible reason.
@MainActor
final class ContractCompatibilityTests: XCTestCase {
    private let appIdentity = (version: "2026.9.20", sha256: String(repeating: "a", count: 64))

    private func engineIdentity(
        version: String,
        sha256: String
    ) -> Components.Schemas.ContractIdentity {
        Components.Schemas.ContractIdentity(version: version, sha256: sha256)
    }

    // MARK: - Agreement

    func testMatchingContractsConnect() {
        let engine = engineIdentity(version: appIdentity.version, sha256: appIdentity.sha256)
        XCTAssertNil(ContractCompatibility.mismatch(engine: engine, app: appIdentity))
    }

    /// The digest is hex; casing is not part of the identity. A case-sensitive
    /// compare here would refuse every connection between two correct builds.
    func testDigestComparisonIgnoresHexCasing() {
        let engine = engineIdentity(
            version: appIdentity.version,
            sha256: appIdentity.sha256.uppercased()
        )
        XCTAssertNil(ContractCompatibility.mismatch(engine: engine, app: appIdentity))
    }

    // MARK: - Cannot be verified

    /// An engine too old to report a contract, or one whose generated identity is
    /// missing. Absence is never read as agreement.
    func testAbsentContractIsRefusedNotAssumedCompatible() {
        XCTAssertEqual(
            ContractCompatibility.mismatch(engine: nil, app: appIdentity),
            .engineDidNotStateContract
        )
    }

    /// An engine that answered without answering. Comparing "" against a real
    /// digest would report a *version* mismatch against a blank version, which
    /// would tell the user to update to nothing.
    func testBlankIdentityIsTreatedAsUnstatedNotAsAVersionMismatch() {
        for (version, sha) in [("", "abc"), ("2026.9.20", ""), ("   ", "   ")] {
            XCTAssertEqual(
                ContractCompatibility.mismatch(
                    engine: engineIdentity(version: version, sha256: sha),
                    app: appIdentity
                ),
                .engineDidNotStateContract,
                "blank version=\(version) sha=\(sha) must read as unstated"
            )
        }
    }

    // MARK: - Version skew

    func testDifferentVersionsAreRefusedAndBothAreNamed() {
        let engine = engineIdentity(version: "2026.9.8", sha256: String(repeating: "b", count: 64))
        let mismatch = ContractCompatibility.mismatch(engine: engine, app: appIdentity)
        XCTAssertEqual(mismatch, .versionDiffers(app: "2026.9.20", engine: "2026.9.8"))

        // Both versions in the message — a refusal naming only one leaves the
        // person unable to tell which machine to touch.
        let headline = try? XCTUnwrap(mismatch?.headline)
        XCTAssertEqual(headline?.contains("2026.9.20"), true)
        XCTAssertEqual(headline?.contains("2026.9.8"), true)
    }

    /// The trap this exists to catch: lexicographically "2026.9.8" > "2026.9.20",
    /// so a plain string compare names the WRONG side as older and sends the user
    /// to update the machine that is already current.
    func testOlderSideUsesNumericOrderingNotLexicographic() {
        XCTAssertGreaterThan("2026.9.8", "2026.9.20", "precondition: the naive compare is wrong")

        let appIsOlder = ContractMismatch.versionDiffers(app: "2026.9.8", engine: "2026.9.20")
        XCTAssertEqual(appIsOlder.olderSide, .app)
        XCTAssertTrue(appIsOlder.detail.contains("2026.9.20"), "must name the version to update TO")

        let engineIsOlder = ContractMismatch.versionDiffers(app: "2026.9.20", engine: "2026.9.8")
        XCTAssertEqual(engineIsOlder.olderSide, .engine)
        XCTAssertTrue(engineIsOlder.detail.contains("2026.9.20"))
    }

    func testOlderSideIsUnorderedWhenNothingCanBeOrdered() {
        XCTAssertNil(ContractMismatch.engineDidNotStateContract.olderSide)
        XCTAssertNil(
            ContractMismatch.sameVersionDifferentContent(
                version: "2026.9.20",
                appSHA256: "a",
                engineSHA256: "b"
            ).olderSide
        )
        // Equal versions cannot be ordered, and the advice must not claim they can.
        let equal = ContractMismatch.versionDiffers(app: "2026.9.20", engine: "2026.9.20")
        XCTAssertNil(equal.olderSide)
        XCTAssertTrue(equal.detail.contains("both"))
    }

    // MARK: - Same version, different content

    /// Its own defect, not a version skew: one version published twice with
    /// different content. "Update to the latest" does not fix it, so it must not
    /// render as a version mismatch.
    func testSameVersionDifferentDigestIsItsOwnFault() {
        let engine = engineIdentity(
            version: appIdentity.version,
            sha256: String(repeating: "c", count: 64)
        )
        let mismatch = ContractCompatibility.mismatch(engine: engine, app: appIdentity)
        XCTAssertEqual(
            mismatch,
            .sameVersionDifferentContent(
                version: "2026.9.20",
                appSHA256: appIdentity.sha256,
                engineSHA256: String(repeating: "c", count: 64)
            )
        )
        let headline = try? XCTUnwrap(mismatch?.headline)
        XCTAssertEqual(headline?.contains("aren't the same build"), true)
        // Distinguishable from a version skew by MESSAGE, not only by case —
        // the person reading it has to be able to tell the two apart.
        XCTAssertNotEqual(
            mismatch?.headline,
            ContractMismatch.versionDiffers(app: "2026.9.20", engine: "2026.9.8").headline
        )
    }

    // MARK: - Every refusal is actionable

    func testEveryMismatchSaysWhatItIsAndWhatToDo() {
        let all: [ContractMismatch] = [
            .engineDidNotStateContract,
            .versionDiffers(app: "2026.9.20", engine: "2026.9.8"),
            .sameVersionDifferentContent(version: "2026.9.20", appSHA256: "a", engineSHA256: "b")
        ]
        for mismatch in all {
            XCTAssertFalse(mismatch.headline.isEmpty, "\(mismatch) has no headline")
            XCTAssertFalse(mismatch.detail.isEmpty, "\(mismatch) has no next step")
            // Never a dead end: every refusal names an action.
            XCTAssertTrue(
                mismatch.detail.lowercased().contains("update"),
                "\(mismatch) must tell the person what to do"
            )
        }
    }

    // MARK: - The app's own identity

    /// The baked identity must be real. A blank or placeholder value would make
    /// every engine look mismatched, or — worse — match another broken build.
    func testAppIdentityIsBakedAndWellFormed() {
        let identity = ContractCompatibility.appIdentity
        XCTAssertFalse(identity.version.isEmpty)
        XCTAssertEqual(identity.sha256.count, 64, "a sha256 digest is 64 hex characters")
        XCTAssertTrue(
            identity.sha256.allSatisfy { $0.isHexDigit },
            "digest must be hex, not a placeholder"
        )
        XCTAssertEqual(identity.version, BakedContractIdentity.version)
        XCTAssertEqual(identity.sha256, BakedContractIdentity.sha256)
    }

    /// An engine reporting exactly what this app baked is the normal case and
    /// must connect — the check has to be satisfiable by the shipped pair.
    func testAnEngineServingThisAppsOwnContractConnects() {
        let engine = engineIdentity(
            version: BakedContractIdentity.version,
            sha256: BakedContractIdentity.sha256
        )
        XCTAssertNil(ContractCompatibility.mismatch(engine: engine))
    }
}
