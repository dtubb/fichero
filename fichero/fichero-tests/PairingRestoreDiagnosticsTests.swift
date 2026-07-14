@testable import Fichero
import XCTest

/// Which of the four persisted values decides "am I still paired?" (#3772)
///
/// The relaunch bug is NOT "we forgot to save it" — all four values are written. The
/// question is which one the restore chain actually depends on, and these pin the
/// answer so it cannot drift back.
final class PairingRestoreDiagnosticsTests: XCTestCase {

    // MARK: - The launch gate: what iOS actually checks

    /// THE DEFECT. iOS decides it is unpaired from the PAIRED LIBRARY PATH alone —
    /// a device token, a saved host and a stored SPKI pin do not enter into it.
    func testIOSLaunchShowsSetupNeededWhenOnlyTheLibraryPathIsMissing() {
        let phase = EngineConfig.iosLaunchPhase(hasPairedLibrary: false, isReachable: true)
        XCTAssertEqual(
            phase,
            .setupNeeded,
            "A reachable, fully-tokened, pinned device is still told to pair again when "
            + "the paired LIBRARY PATH is absent. That single UserDefaults string is the "
            + "whole gate (#3772)."
        )
    }

    /// With the library path present, the same device is treated as paired.
    func testIOSLaunchIsReadyOnceTheLibraryPathIsPresent() {
        XCTAssertEqual(EngineConfig.iosLaunchPhase(hasPairedLibrary: true, isReachable: true), .ready)
        XCTAssertEqual(EngineConfig.iosLaunchPhase(hasPairedLibrary: true, isReachable: false), .unreachable)
    }

    // MARK: - The snapshot's verdict

    private func snapshot(
        host: String? = "https://mac.local:8765",
        hasToken: Bool = true,
        hasSPKIPin: Bool = true,
        libraryPath: String? = "/Users/d/Documents/L.fichero"
    ) -> PairingRestoreSnapshot {
        PairingRestoreSnapshot(
            host: host,
            hasToken: hasToken,
            tokenAccessibility: nil,
            hasSPKIPin: hasSPKIPin,
            libraryPath: libraryPath
        )
    }

    func testAllFourPresentMeansTheConnectionIsAtFault() {
        XCTAssertTrue(snapshot().isFullyRestored)
        XCTAssertTrue(snapshot().verdict.contains("ALL FOUR RESTORED"))
    }

    func testMissingTokenIsNamedAsAKeychainProblem() {
        XCTAssertTrue(snapshot(hasToken: false).verdict.contains("TOKEN MISSING"))
    }

    func testMissingPinIsNamedAsAPinnedTransportProblem() {
        XCTAssertTrue(snapshot(hasSPKIPin: false).verdict.contains("PIN MISSING"))
    }

    /// The case the issue missed: the Keychain outlives an iOS reinstall but
    /// UserDefaults does not — so a good token is keyed to a host we no longer know,
    /// and it can never be looked up again.
    func testTokenWithoutHostIsNamedAnOrphanedToken() {
        XCTAssertTrue(snapshot(host: nil, hasToken: true).verdict.contains("ORPHANED TOKEN"))
    }

    func testNoHostAndNoTokenIsNamedAHostProblem() {
        XCTAssertTrue(snapshot(host: nil, hasToken: false).verdict.contains("HOST MISSING"))
    }

    /// A missing library path does NOT make the snapshot "unrestored" — the token,
    /// host and pin are what a connection needs. That mismatch between what the
    /// snapshot considers restored and what iOS's launch gate checks IS the bug.
    func testLibraryPathIsNotRequiredToReconnect() {
        XCTAssertTrue(snapshot(libraryPath: nil).isFullyRestored)
    }
}
