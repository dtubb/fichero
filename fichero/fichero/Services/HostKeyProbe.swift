import CryptoKit
import FicheroAPIClient
import Foundation

/// First contact with a typed address (`sharing.people.sign-in-without-a-code`, Step 8.9): with no link there is no pin, so the
/// guest reads the key the host presents, shows its fingerprint once, and pairs pinned to it only when the person trusts it.
/// The host's Sharing pane shows the same fingerprint, so the two can be compared.
nonisolated enum HostKeyFingerprint {
    /// A key read at first contact, waiting for the person to trust it.
    struct Ask: Equatable {
        let url: URL
        let pin: String
        let fingerprint: String
    }

    /// The trust alert's sentence: where to compare, and what a different key means.
    static func trustSentence(host: String, fingerprint: String) -> String {
        "Fichero hasn't connected to \(host) before. Its key is \(fingerprint). If Settings › Sharing on \(host) shows the "
            + "same key, trust it. If not, another computer is answering to that name: don't connect."
    }

    /// The pin as a person reads it: the first 8 bytes of the key's SHA-256 as four groups of four hex digits
    /// ("3F2A 91C0 7B44 E1D9"). Either pin form (`sha256/…` or the raw SPKI) gives the same text; nil for no pin.
    static func text(ofPin pin: String) -> String? {
        guard let normalized = try? RemoteCertificatePinning.validatedSPKIPin(pin) else { return nil }
        let digest: Data
        if normalized.hasPrefix("sha256/") {
            guard let hash = Data(base64Encoded: String(normalized.dropFirst("sha256/".count))) else { return nil }
            digest = hash
        } else {
            guard let spki = Data(base64Encoded: normalized) else { return nil }
            digest = Data(SHA256.hash(data: spki))
        }
        var rest = Substring(digest.prefix(8).map { String(format: "%02X", $0) }.joined())
        var groups: [String] = []
        while !rest.isEmpty {
            groups.append(String(rest.prefix(4)))
            rest = rest.dropFirst(4)
        }
        return groups.joined(separator: " ")
    }
}

nonisolated enum HostKeyProbe {
    /// The `sha256/…` pin of the key `url` presents, read with nothing sent (`RemoteCertificatePinning.presentedSHA256Pin`).
    static func sha256Pin(at url: URL) async throws -> String {
        try await RemoteCertificatePinning.presentedSHA256Pin(at: url)
    }

    /// A typed address (`studio.local`, `10.10.10.1:8765`, `https://studio.local:8765`), not a link: https is assumed and an
    /// address of this Mac's kind with no port gets the engine's (`validatedRemoteURL`). Nil for a link, a payload or junk.
    @MainActor static func typedAddress(_ text: String) -> URL? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !trimmed.hasPrefix("{"), !trimmed.lowercased().hasPrefix("fichero:"),
              !trimmed.contains("?"), !trimmed.contains(" ") else { return nil }
        let withScheme = trimmed.contains("://") ? trimmed : "https://\(trimmed)"
        return try? validatedRemoteURL(from: withScheme, allowLocalhost: false, requireSecureTransportForRemote: true)
    }
}
