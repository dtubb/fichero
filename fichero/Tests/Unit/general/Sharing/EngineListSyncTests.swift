@testable import Fichero
import Foundation
import Testing

/// multiuser.remote-flow-no-pairing-code (#2403): a new device reads the synced list (the own-devices item) and signs in
/// by the synced key at its addresses; the enrollment secret is the path only when the key is absent or refused.
struct EngineListSyncTests {
    private let item = OwnDevicesItem(
        engineID: "eng-1", macName: "Daniel's MacBook Air",
        addresses: [.init(url: "https://air.local:8443", spki: "pin"), .init(url: "https://air.tail1.ts.net", spki: nil)],
        enrollmentSecret: "secret")

    private final class Calls: @unchecked Sendable {
        var keyed: [String] = []
        var enrolled: [String] = []
    }

    private func enroll(_ calls: Calls) -> (OwnDevicesItem.Address, String, String) async throws -> (token: String, expiresAt: Date) {
        { address, _, _ in
            calls.enrolled.append(address.url)
            return ("device-token", Date(timeIntervalSince1970: 1_900_000_000))
        }
    }

    @Test func testNewDeviceDialsFromTheSyncedListWithoutACode() async throws {
        let calls = Calls()
        let outcome = try await OwnDevicesKeyDial.connect(item, deviceName: "iPhone", keySignIn: { address in
            calls.keyed.append(address.url)
            if address.url.hasSuffix(".ts.net") { throw URLError(.timedOut) }
            return "session"
        }, enroll: enroll(calls))
        #expect(calls.keyed == ["https://air.tail1.ts.net", "https://air.local:8443"])
        #expect(outcome == .session(address: item.addresses[0], token: "session"))
        #expect(calls.enrolled.isEmpty)
    }

    @Test func aRefusedKeyStopsTheKeyDialAndEnrolsBySecret() async throws {
        let calls = Calls()
        let outcome = try await OwnDevicesKeyDial.connect(item, deviceName: "iPhone", keySignIn: { address in
            calls.keyed.append(address.url)
            throw SignInRefusal.refused(statusCode: 401)
        }, enroll: enroll(calls))
        #expect(calls.keyed == ["https://air.tail1.ts.net"])
        #expect(calls.enrolled == ["https://air.tail1.ts.net"])
        guard case .enrolled = outcome else { Issue.record("expected enrolment, got \(outcome)"); return }
    }

    @Test func noSyncedKeyEnrolsBySecret() async throws {
        let calls = Calls()
        let outcome = try await OwnDevicesKeyDial.connect(item, deviceName: "iPhone", keySignIn: nil, enroll: enroll(calls))
        #expect(calls.enrolled == ["https://air.tail1.ts.net"])
        guard case .enrolled = outcome else { Issue.record("expected enrolment, got \(outcome)"); return }
    }
}
