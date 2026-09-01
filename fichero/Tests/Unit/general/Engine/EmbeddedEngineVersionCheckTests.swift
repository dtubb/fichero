@testable import Fichero
import Foundation
import Testing

/// The launch-time engine version check (Daniel, 2026-09-01: "Why is an old one
/// embedded? We need a launch engine version check, so that's flagged").
///
/// The comparison is the whole feature and it is pure, so it is tested
/// directly — no engine, no bundle, no window. The two halves that cannot be
/// reached from a unit test (the embed phase writing the stamps, and the
/// banner mounting) are guarded by `scripts/check_engine_version_stamp.py` and
/// by the source assertions at the bottom.
struct EmbeddedEngineVersionCheckTests {

    private func source(_ path: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8)
    }

    private func stamps(_ embedded: String?, _ expected: String?) -> EmbeddedEngineVersionCheck.Stamps {
        EmbeddedEngineVersionCheck.Stamps(embedded: embedded, expected: expected)
    }

    // MARK: - The ruling

    @Test("Everything agreeing is a match")
    func agreementMatches() {
        let verdict = EmbeddedEngineVersionCheck.verdict(
            isEmbedded: true,
            reportedVersion: "2026.9.1b2",
            stamps: stamps("2026.9.1b2", "2026.9.1b2")
        )
        #expect(verdict == .matches("2026.9.1b2"))
        #expect(EmbeddedEngineVersionCheck.warning(for: verdict) == nil)
    }

    /// The exact 2026-09-01 shape: the engine that answers is the one that was
    /// embedded, and BOTH are older than the checkout the app was built from.
    /// Comparing only the running engine against the embedded stamp would call
    /// this clean — which is precisely the silence being fixed.
    @Test("A stale stage embedded from a moved-on checkout is a mismatch")
    func staleStageIsFlagged() {
        let verdict = EmbeddedEngineVersionCheck.verdict(
            isEmbedded: true,
            reportedVersion: "2026.8.27",
            stamps: stamps("2026.8.27", "2026.9.1b2")
        )
        #expect(verdict == .mismatch(running: "2026.8.27", expected: "2026.9.1b2"))
        #expect(
            EmbeddedEngineVersionCheck.warning(for: verdict)
                == "Embedded engine is 2026.8.27, app expected 2026.9.1b2 — restage the engine."
        )
    }

    @Test("An engine answering with a version we never embedded is a mismatch")
    func foreignEngineIsFlagged() {
        let verdict = EmbeddedEngineVersionCheck.verdict(
            isEmbedded: true,
            reportedVersion: "2026.7.1",
            stamps: stamps("2026.9.1b2", "2026.9.1b2")
        )
        #expect(verdict == .mismatch(running: "2026.7.1", expected: "2026.9.1b2"))
    }

    @Test("A remote or dev-external engine is not this check's business")
    func notEmbeddedIsNotApplicable() {
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: false,
                reportedVersion: "2026.1.1",
                stamps: stamps("2026.9.1b2", "2026.9.1b2")
            ) == .notApplicable
        )
    }

    @Test("No reported version means nothing to compare, not a mismatch")
    func silentEngineIsNotApplicable() {
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: true,
                reportedVersion: nil,
                stamps: stamps("2026.9.1b2", "2026.9.1b2")
            ) == .notApplicable
        )
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: true,
                reportedVersion: "",
                stamps: stamps("2026.9.1b2", "2026.9.1b2")
            ) == .notApplicable
        )
    }

    /// Blind is not clean. An unstamped bundle must report its own blindness
    /// rather than silently certifying whatever engine turns up.
    @Test("No stamps at all is `unstamped`, never a match")
    func unstampedIsItsOwnVerdict() {
        let verdict = EmbeddedEngineVersionCheck.verdict(
            isEmbedded: true,
            reportedVersion: "2026.9.1b2",
            stamps: .unstamped
        )
        #expect(verdict == .unstamped)
        #expect(EmbeddedEngineVersionCheck.warning(for: verdict) == nil)
    }

    /// A half-stamped bundle is a STAMPING bug. Accusing the engine of a
    /// mismatch against an absent value would send the reader to restage an
    /// engine that is perfectly current.
    @Test("One stamp missing falls back to the other instead of accusing the engine")
    func halfStampedDoesNotFalselyAccuse() {
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: true,
                reportedVersion: "2026.9.1b2",
                stamps: stamps(nil, "2026.9.1b2")
            ) == .matches("2026.9.1b2")
        )
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: true,
                reportedVersion: "2026.9.1b2",
                stamps: stamps("2026.9.1b2", nil)
            ) == .matches("2026.9.1b2")
        )
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: true,
                reportedVersion: "2026.8.27",
                stamps: stamps(nil, "2026.9.1b2")
            ) == .mismatch(running: "2026.8.27", expected: "2026.9.1b2")
        )
    }

    /// Empty strings are the shape a PlistBuddy `Add` produces when its source
    /// read came back empty — treated as absent, not as a version to match.
    @Test("Empty stamps are absent, not a version")
    func emptyStampsAreAbsent() {
        #expect(
            EmbeddedEngineVersionCheck.verdict(
                isEmbedded: true,
                reportedVersion: "2026.9.1b2",
                stamps: stamps("", "")
            ) == .unstamped
        )
    }

    // MARK: - The wiring the unit test cannot execute

    @Test("The stamping script and the runtime check name the same Info.plist keys")
    func keysAgreeWithTheStampingScript() throws {
        let script = try String(
            contentsOf: AppSource.root()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("scripts/stamp_engine_version_into_app.sh"),
            encoding: .utf8
        )
        #expect(script.contains(EmbeddedEngineVersionCheck.embeddedVersionKey))
        #expect(script.contains(EmbeddedEngineVersionCheck.expectedVersionKey))
    }

    @Test("The check runs on the ready path and drives the banner")
    func readyPathRunsTheCheck() throws {
        let readiness = try source("App/AppState+Readiness.swift")
        #expect(readiness.contains("await verifyEmbeddedEngineVersion()"))
        #expect(readiness.contains("engineVersionWarning ="))

        let notice = try source("Views/Shell/EngineVersionMismatchNotice.swift")
        #expect(notice.contains("appState.engineVersionWarning"))
        #expect(notice.contains("appState.engineVersionWarningDismissed"))

        // Mounted above the window content, not behind a search or a mode.
        let host = try source("Views/Shell/DocumentTabView.swift")
        #expect(host.contains("EngineVersionMismatchNotice()"))
    }
}
