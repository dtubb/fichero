//
//  HeartbeatRetriesClosedConnectionTests.swift
//  FicheroTests
//
//  #6372 -- the engine closed an idle pooled connection between two health probes, the next probe died on it, and the status flipped to
//  `notResponding` for a whole 5 s interval. The probe retries ONCE at once on a fresh connection when its error is a closed or reset
//  connection (`engine.health.probe-survives-a-closed-keep-alive`); these pin which errors count, so any other failure still fails closed.
//

@testable import Fichero
import Foundation
import Testing

@Suite("The health probe retries a closed connection once (#6372)")
struct HeartbeatRetriesClosedConnectionTests {
    private struct RemoteConnectionClosed: Error, CustomStringConvertible {
        var description: String { "HTTPClientError.remoteConnectionClosed" }
    }

    @Test("a connection the engine closed or reset is retried")
    func closedConnectionsAreRetried() {
        #expect(EngineReadinessProbe.isClosedConnection(RemoteConnectionClosed()))
        #expect(EngineReadinessProbe.isClosedConnection(URLError(.networkConnectionLost)))
        #expect(EngineReadinessProbe.isClosedConnection(NSError(domain: NSPOSIXErrorDomain, code: Int(ECONNRESET), userInfo: [
            NSLocalizedDescriptionKey: "Connection reset by peer"
        ])))
    }

    @Test("a timeout, a refused connection or a bad certificate is not retried")
    func otherFailuresFailClosed() {
        #expect(!EngineReadinessProbe.isClosedConnection(URLError(.timedOut)))
        #expect(!EngineReadinessProbe.isClosedConnection(URLError(.cannotConnectToHost)))
        #expect(!EngineReadinessProbe.isClosedConnection(URLError(.serverCertificateUntrusted)))
    }
}
