import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

/// Somewhere for a background pipe drain to put its bytes. `@unchecked` is
/// honest here: the semaphore, not the type, is what orders the write against
/// the read.
private final class DataBox: @unchecked Sendable {
    var value = Data()
}

#if os(macOS)
extension EmbeddedBackendService {
    // MARK: - TLS material cache (#3936)

    /// What is worth remembering between launches: the paths the engine derived.
    /// Deliberately NOT the pin — see `prepareTLSMaterial`.
    private struct CachedTLSPaths: Codable {
        let bindHost: String
        let certificatePath: String
        let keyPath: String
    }

    private static let tlsCacheDefaultsPrefix = "fichero.engine.tls_material|"

    /// Everything that could change WHICH material the engine hands back: the
    /// arguments (host / port / public URL / alt hosts) and the engine binary's
    /// own identity. The binary matters because an engine update could change how
    /// the material directory is derived, and a stale path would leave us pinning
    /// a certificate the new engine no longer serves.
    private static func tlsCacheKey(executablePath: String, arguments: [String]) -> String? {
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: executablePath),
              let size = attrs[.size] as? Int,
              let modified = attrs[.modificationDate] as? Date else {
            return nil  // Can't identify the binary → don't risk a stale cache.
        }
        let engineIdentity = "\(executablePath)|\(size)|\(modified.timeIntervalSince1970)"
        return tlsCacheDefaultsPrefix + "\(engineIdentity)|\(arguments.joined(separator: " "))"
    }

    private static func cachedTLSMaterial(forKey key: String) -> RemoteAccessTLSMaterial? {
        guard let data = UserDefaults.standard.data(forKey: key),
              let paths = try? JSONDecoder().decode(CachedTLSPaths.self, from: data),
              FileManager.default.fileExists(atPath: paths.certificatePath),
              FileManager.default.fileExists(atPath: paths.keyPath) else {
            return nil
        }
        // The pin comes from the certificate ON DISK, never from the cache, so it
        // cannot be stale against a rotated cert.
        guard let pin = try? spkiPin(ofCertificateAtPath: paths.certificatePath) else {
            logger.warning("Cached TLS cert unreadable — falling back to the engine (#3936)")
            return nil
        }
        return RemoteAccessTLSMaterial(
            bindHost: paths.bindHost,
            certificatePath: paths.certificatePath,
            keyPath: paths.keyPath,
            spkiPin: pin
        )
    }

    private static func storeTLSMaterial(_ material: RemoteAccessTLSMaterial, forKey key: String) {
        let paths = CachedTLSPaths(
            bindHost: material.bindHost,
            certificatePath: material.certificatePath,
            keyPath: material.keyPath
        )
        guard let data = try? JSONEncoder().encode(paths) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    /// The engine's `_spki_pin_from_certificate` in Swift: PEM → DER → the
    /// certificate's SubjectPublicKeyInfo, base64. Byte-identical by construction
    /// — the engine base64-encodes the same SPKI DER, and
    /// `RemoteCertificatePinning.spkiPin(for:)` is the same encoding the pinning
    /// layer validates against.
    static func spkiPin(ofCertificateAtPath path: String) throws -> String {
        let pem = try String(contentsOfFile: path, encoding: .utf8)
        guard let der = derFromPEM(pem),
              let certificate = SecCertificateCreateWithData(nil, der as CFData),
              let publicKey = SecCertificateCopyKey(certificate) else {
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: 3,
                    userInfo: [NSLocalizedDescriptionKey: "Could not read the engine's TLS certificate."]
                )
            )
        }
        return try RemoteCertificatePinning.spkiPin(for: publicKey)
    }

    /// Strip the PEM armour and decode. Mirrors the engine's `_pem_to_der`.
    static func derFromPEM(_ pem: String) -> Data? {
        let body = pem
            .split(separator: "\n")
            .filter { !$0.contains("BEGIN CERTIFICATE") && !$0.contains("END CERTIFICATE") }
            .joined()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return Data(base64Encoded: body, options: .ignoreUnknownCharacters)
    }

    // Promoted from `private` to internal: called by launchEmbeddedBackend in
    // the Spawn extension file.
    func prepareLocalAccessTLSMaterial(executablePath: String) async throws -> RemoteAccessTLSMaterial {
        try await prepareTLSMaterial(
            executablePath: executablePath,
            arguments: ["--prepare-local-access"],
            failureMessage: "Local engine TLS preparation failed."
        )
    }

    // Promoted from `private` to internal: called by launchEmbeddedBackend in
    // the Spawn extension file.
    func prepareRemoteAccessTLSMaterial(
        executablePath: String,
        publicBaseURL: URL
    ) async throws -> RemoteAccessTLSMaterial {
        try await prepareTLSMaterial(
            executablePath: executablePath,
            arguments: [
                "--prepare-remote-access",
                "--public-base-url",
                publicBaseURL.absoluteString
            ],
            failureMessage: "Remote access TLS preparation failed."
        )
    }

    /// TLS material for the engine, WITHOUT paying for the engine to tell us
    /// (#3936).
    ///
    /// `remote_access_tls.py` only generates when the cert or key is MISSING —
    /// otherwise it re-reads the existing cert, re-derives the pin, and returns.
    /// So every launch after the first spawned the whole 1.0GB engine binary, on
    /// the main actor, to learn something already on disk. Measured at 2.74s.
    ///
    /// The paths are the only thing we cannot compute (the engine derives the
    /// material directory from host/port/URL/alt-hosts), so those are cached. The
    /// SPKI pin is NOT cached — it is re-derived from the certificate file on
    /// every launch, which is a file read and a parse. That is both cheaper than
    /// a subprocess and strictly safer than caching a pin and guessing at
    /// staleness with mtime/size: a rotated cert produces a new pin automatically,
    /// because the pin is only ever read from the cert actually on disk.
    ///
    /// The cache key includes the engine binary's identity, so an engine update
    /// that changed the material-directory derivation invalidates it — otherwise
    /// we could pin a cert from a directory the new engine no longer serves.
    private func prepareTLSMaterial(
        executablePath: String,
        arguments: [String],
        failureMessage: String
    ) async throws -> RemoteAccessTLSMaterial {
        let cacheKey = Self.tlsCacheKey(executablePath: executablePath, arguments: arguments)
        if let cacheKey, let cached = Self.cachedTLSMaterial(forKey: cacheKey) {
            LaunchProfile.milestone("engine TLS material reused (no subprocess)")
            logger.info("TLS material reused from cache — engine subprocess skipped (#3936)")
            return cached
        }

        // #3936: the subprocess spawns the ~1GB engine and blocks on
        // `waitUntilExit()` for ~2.74s. On a cache HIT (above) we skip it, but on a
        // MISS — every user's first launch, and EVERY dev launch (the mtime-keyed
        // cache invalidates on each engine rebuild) — it used to freeze the main
        // actor and stall first frame. Run it OFF the main actor; only the cheap
        // cache lookup + pin re-derivation stay on main.
        let material = try await Task.detached(priority: .userInitiated) {
            try Self.runEngineTLSPrep(
                executablePath: executablePath,
                arguments: arguments,
                failureMessage: failureMessage
            )
        }.value
        if let cacheKey {
            Self.storeTLSMaterial(material, forKey: cacheKey)
        }
        return material
    }

    /// The subprocess path: only when the material genuinely has to be generated
    /// (first launch, rotated cert, engine update).
    /// nonisolated + static (#3936): self-contained (local Process/pipes only), so
    /// it can run off the @MainActor in a detached task without blocking first frame.
    nonisolated private static func runEngineTLSPrep(
        executablePath: String,
        arguments: [String],
        failureMessage: String
    ) throws -> RemoteAccessTLSMaterial {
        let tlsPhase = LaunchProfile.beginPhase("engine TLS prep (subprocess)")
        defer { LaunchProfile.endPhase("engine TLS prep (subprocess)", tlsPhase) }
        LaunchProfile.milestone("engine TLS prep — spawning engine")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = arguments

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()

        // Drain BOTH pipes concurrently, and BEFORE waiting. Waiting first
        // deadlocks forever the moment the child writes more than the ~64KB pipe
        // buffer: it blocks in write() waiting for a reader that is blocked in
        // waitUntilExit() waiting for it to exit. Draining them in sequence has
        // the same bug on the pipe not currently being read.
        let errorBox = DataBox()
        let drained = DispatchSemaphore(value: 0)
        let errorHandle = stderr.fileHandleForReading
        DispatchQueue.global(qos: .userInitiated).async {
            errorBox.value = errorHandle.readDataToEndOfFile()
            drained.signal()
        }
        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        drained.wait()
        let errorData = errorBox.value

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let message = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
                ?? failureMessage
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: Int(process.terminationStatus),
                    userInfo: [NSLocalizedDescriptionKey: message]
                )
            )
        }

        do {
            return try JSONDecoder().decode(RemoteAccessTLSMaterial.self, from: outputData)
        } catch {
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "Could not decode remote access TLS material."]
                )
            )
        }
    }
}
#endif
