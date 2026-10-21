@testable import Fichero
import XCTest

/// `m2p.ios.connect-failure-offers-recovery`: every phase in which the connection is not working offers Reconnect and Change
/// Server; the working and starting phases do not. Not run on the Pro (no simulator); the M4/builder runs it.
final class IOSConnectionRecoveryPolicyTests: XCTestCase {
    func testEveryFailurePhaseOffersRecovery() {
        let failing: [EngineSession.Phase] = [
            .portConflict(pid: nil), .portConflict(pid: 42), .authRejected(diagnosis: "x"),
            .unreachable(diagnosis: "x"), .failed(diagnosis: "x"),
        ]
        for phase in failing {
            XCTAssertTrue(IOSConnectionRecoveryPolicy.offersRecovery(phase: phase), "\(phase)")
        }
    }

    func testAWorkingStartingOrUnpairedConnectionDoesNot() {
        for phase in [EngineSession.Phase.ready, .starting, .setupNeeded] {
            XCTAssertFalse(IOSConnectionRecoveryPolicy.offersRecovery(phase: phase), "\(phase)")
        }
    }
}
