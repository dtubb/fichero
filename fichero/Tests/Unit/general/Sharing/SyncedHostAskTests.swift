@testable import Fichero
import Foundation
import Testing

/// #5898 guest half (sharing.synced-device-pairs-by-host-code): the ask is once per project, takes the LINK only.
struct SyncedHostAskTests {
    private let record = SyncedHostRecord(hostURL: "https://studio.tail1234.ts.net", hostName: "Studio", person: "Ana")

    @Test func asksOnlyWhileNoTokenAndNotDismissed() {
        #expect(SyncedHostAsk.needsAsk(record, hasToken: { _ in false }, dismissed: false))
        #expect(!SyncedHostAsk.needsAsk(record, hasToken: { _ in true }, dismissed: false))
        #expect(!SyncedHostAsk.needsAsk(record, hasToken: { _ in false }, dismissed: true))
        #expect(!SyncedHostAsk.needsAsk(nil, hasToken: { _ in false }, dismissed: false))
    }

    @Test func theSentenceNamesTheHostAndThePerson() {
        #expect(SyncedHostAsk.sentence(record) == "This project is hosted on Studio. Ask Ana for a pairing link.")
    }

    @Test func aBareCodeIsRefusedInWords() {
        #expect(throws: SyncedHostAskError.notALink) { try SyncedHostAsk.fields(fromLink: "ABCD-1234", record: record) }
    }

    @Test func aLinkForAnotherMacIsRefused() throws {
        let other = SyncedHostRecord(hostURL: "https://other.tail1234.ts.net", hostName: "Other", person: "Bo")
        let payload = PairingQRCodePayload(version: 1, apiURL: "https://studio.tail1234.ts.net", pairCode: "ABCD1234",
                                           expiresAt: Date().addingTimeInterval(300), spki: nil, libraryPath: "/L")
        let link = try RemoteClientPairing.inviteLinkString(from: payload)
        #expect(throws: SyncedHostAskError.otherHost("Other")) { try SyncedHostAsk.fields(fromLink: link, record: other) }
    }

    @Test func refusalsSayWhich() {
        #expect(SyncedHostAsk.words(forStatus: 401, detail: "invalid or expired pairing code").contains("used, has expired"))
        #expect(SyncedHostAsk.words(forStatus: 401, detail: "person required: x").contains("who you are"))
        #expect(SyncedHostAsk.words(forStatus: 429, detail: nil).contains("Too many"))
    }

    @Test func dismissedIsPerProject() throws {
        let defaults = try #require(UserDefaults(suiteName: "SyncedHostAskTests"))
        defaults.removePersistentDomain(forName: "SyncedHostAskTests")
        let a = URL(fileURLWithPath: "/tmp/A.fichero"), b = URL(fileURLWithPath: "/tmp/B.fichero")
        SyncedHostAsk.dismiss(a, defaults: defaults)
        #expect(SyncedHostAsk.isDismissed(a, defaults: defaults))
        #expect(!SyncedHostAsk.isDismissed(b, defaults: defaults))
    }
}
