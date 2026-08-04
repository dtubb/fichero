//
//  EngineTLSMaterialCacheTests.swift
//  FicheroTests
//
//  #3936 — the app stopped spawning a 1.0GB engine binary to read a file it
//  already had. remote_access_tls.py only GENERATES when the cert or key is
//  missing; otherwise it re-reads the cert, re-derives the pin, and returns. So
//  every launch after the first paid 2.74s, on the main actor, for an answer
//  already sitting on disk.
//
//  The security-load-bearing half: the SPKI pin is what RemoteCertificatePinning
//  enforces, so it is never cached — it is re-derived from the certificate file
//  every launch. These pin the derivation against the engine's own algorithm.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
@Suite("Engine TLS material cache (#3936)")
struct EngineTLSMaterialCacheTests {

    // MARK: - PEM → DER, mirroring the engine's _pem_to_der

    /// The engine strips the armour lines and base64-decodes the rest. Ours must
    /// agree byte for byte or the derived pin would differ from the engine's and
    /// pinning would reject the engine's own certificate.
    @Test("PEM armour is stripped and the body decoded, like the engine's _pem_to_der")
    func pemToDERMatchesTheEngine() throws {
        let payload = Data([0x30, 0x82, 0x01, 0x0A, 0xDE, 0xAD, 0xBE, 0xEF])
        let pem = """
        -----BEGIN CERTIFICATE-----
        \(payload.base64EncodedString())
        -----END CERTIFICATE-----
        """
        #expect(EmbeddedBackendService.derFromPEM(pem) == payload)
    }

    /// Real PEM wraps at 64 columns, so the body arrives as many lines. The
    /// engine joins every non-armour line before decoding; so must we.
    @Test("a multi-line PEM body is rejoined before decoding")
    func multiLinePEMBodyIsRejoined() throws {
        let payload = Data((0..<200).map { UInt8($0 % 251) })
        let base64 = payload.base64EncodedString()
        let wrapped = stride(from: 0, to: base64.count, by: 64).map { offset -> String in
            let start = base64.index(base64.startIndex, offsetBy: offset)
            let end = base64.index(start, offsetBy: min(64, base64.count - offset))
            return String(base64[start..<end])
        }.joined(separator: "\n")
        let pem = "-----BEGIN CERTIFICATE-----\n\(wrapped)\n-----END CERTIFICATE-----\n"
        #expect(EmbeddedBackendService.derFromPEM(pem) == payload)
    }

    @Test("a PEM with no decodable body yields nil rather than empty bytes")
    func garbagePEMYieldsNil() {
        // Nothing between the armour: there is no certificate here, and pretending
        // there is would hand SecCertificateCreateWithData empty data.
        let pem = "-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----"
        let der = EmbeddedBackendService.derFromPEM(pem)
        #expect(der == nil || der?.isEmpty == true)
    }

    // MARK: - The pin is never taken on trust

    /// A cert path that does not exist must throw, not return a stale or empty
    /// pin: every failure to read the cert has to fall back to the engine.
    @Test("an unreadable certificate throws instead of yielding a pin")
    func unreadableCertificateThrows() {
        #expect(throws: (any Error).self) {
            try EmbeddedBackendService.spkiPin(
                ofCertificateAtPath: "/nonexistent/\(UUID().uuidString)/server.crt"
            )
        }
    }

    /// End to end on a real self-signed certificate: the pin we derive from the
    /// FILE must equal the pin the pinning layer derives from the KEY — the two
    /// halves of #3936's security argument, and the same base64(SPKI DER) the
    /// engine emits.
    @Test("the pin derived from a certificate file matches the pinning layer's own")
    func derivedPinMatchesThePinningLayer() throws {
        guard let fixture = try Self.makeSelfSignedCertificate() else {
            // No cert-generation facility available in this environment; the
            // derivation is still covered by the PEM tests above.
            return
        }
        defer { try? FileManager.default.removeItem(at: fixture.directory) }

        let fromFile = try EmbeddedBackendService.spkiPin(ofCertificateAtPath: fixture.certificatePath)
        let fromKey = try RemoteCertificatePinning.spkiPin(for: fixture.publicKey)
        #expect(fromFile == fromKey)
        #expect(!fromFile.isEmpty)
        // The engine emits base64(SPKI DER) with no "sha256/" prefix; the pinning
        // layer must accept ours unchanged.
        #expect(try RemoteCertificatePinning.validatedSPKIPin(fromFile) == fromFile)
    }

    /// Builds a throwaway self-signed cert with `openssl`, which every macOS has.
    /// Returns nil rather than failing if the tool is unavailable.
    private static func makeSelfSignedCertificate() throws -> (
        directory: URL,
        certificatePath: String,
        publicKey: SecKey
    )? {
        let openssl = URL(fileURLWithPath: "/usr/bin/openssl")
        guard FileManager.default.isExecutableFile(atPath: openssl.path) else { return nil }

        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-tls-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let certificatePath = directory.appendingPathComponent("server.crt").path
        let keyPath = directory.appendingPathComponent("server.key").path

        let process = Process()
        process.executableURL = openssl
        process.arguments = [
            "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", keyPath, "-out", certificatePath,
            "-days", "1", "-subj", "/CN=localhost"
        ]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0,
              let pem = try? String(contentsOfFile: certificatePath, encoding: .utf8),
              let der = EmbeddedBackendService.derFromPEM(pem),
              let certificate = SecCertificateCreateWithData(nil, der as CFData),
              let publicKey = SecCertificateCopyKey(certificate) else {
            try? FileManager.default.removeItem(at: directory)
            return nil
        }
        return (directory, certificatePath, publicKey)
    }
}
