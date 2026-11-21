@testable import Fichero
import Testing

/// signin.password-comes-last / multiuser.password-comes-last (#6568, #2403): the iPhone Connect screen's sections, in order.
struct SignInOptionsOrderTests {
    @Test func theConnectScreenShowsYourMacsThenNearbyMacsThenTheQR() {
        #expect(SignInOptions.connectScreenRows(hasOwnMacs: true) == [.ownMacs, .nearbyMacs, .qrCode])
    }

    @Test func withoutAnOwnDevicesItemTheNearbyMacsLead() {
        #expect(SignInOptions.connectScreenRows(hasOwnMacs: false) == [.nearbyMacs, .qrCode])
    }

    /// The silent key shows nothing, and the password is the host's alert after a typed address, so neither is a row.
    @Test func theRowsAreTheRuledOrderWithoutTheSilentKeyOrThePassword() {
        let ruled = SignInOptions.order(hasSyncedKey: true, hasOwnMacs: true, canApprove: false, nearbyMacs: true, hasPasskey: false)
        #expect(SignInOptions.connectScreenRows(hasOwnMacs: true) == ruled.filter { $0 != .silentKey && $0 != .password })
    }
}
