import FicheroAPIClient
import Foundation
#if canImport(UIKit)
import UIKit
#endif

//  Extracted for file_length (#5113). Byte-for-byte, behaviour unchanged. Imports are the
//  SOURCE file's; the path was asserted free before writing.

//  These two moved WITH the flow, not with the types: Swift's `private` is FILE-scoped, so a
//  `private struct` left behind in RemoteClientPairing.swift was 'inaccessible due to private
//  protection level' from here — nine uses across this file, one in the original, which was
//  its own declaration. Promoting them to internal would have traded encapsulation for a
//  line count; moving them keeps both.

private struct PairingInviteLink {
    static let scheme = "fichero"
    static let host = "pair"
    static let payloadQueryItem = "payload"

    static let queryValueAllowedCharacters: CharacterSet = {
        var allowed = CharacterSet.urlQueryAllowed
        allowed.remove(charactersIn: "+/=")
        return allowed
    }()
}

/// The universal-link form of a pairing invite (#3791): `https://fichero.app/pair?payload=…`.
/// Same `payload` query as the custom-scheme link — the domain is only a name
/// the app claims via Associated Domains so a tapped link resolves even where the
/// `fichero://` scheme isn't registered (e.g. Mail on a colleague's device). The
/// token is still redeemed peer-to-peer against the host in the payload, never
/// against the domain.
private struct PairingUniversalLink {
    static let scheme = "https"
    static let host = "fichero.app"
    static let path = "/pair"
}

enum RemoteClientPairing {
    static func isAcceptableHealthStatus(_ status: String) -> Bool {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "healthy" || normalized == "ok"
    }

    @MainActor
    static func defaultDeviceName() -> String {
        #if canImport(UIKit)
        return UIDevice.current.name
        #else
        return Host.current().localizedName ?? ProcessInfo.processInfo.hostName
        #endif
    }

    static func pairingFields(from message: String) throws -> RemoteClientPairingFields {
        let payload = try PairingQRCodePayloadDecoder.decode(message: message)
        return try pairingFields(from: payload)
    }

    static func pairingFields(fromInviteOrPayload message: String) throws -> RemoteClientPairingFields {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        if looksLikeInviteLink(trimmed) {
            guard let payload = payloadFromInviteLink(trimmed) else {
                throw RemoteClientPairingError.invalidInviteLink
            }
            return try pairingFields(from: payload)
        }
        return try pairingFields(from: trimmed)
    }

    static func inviteLinkString(from payload: PairingQRCodePayload) throws -> String {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        // Sorted keys: JSONEncoder orders keys per PROCESS otherwise (three launches, three orders, 2026-10-31), so two
        // copies of one link differed by eye and the QR's bytes differed from the link's (`sharing.qr-drawn-once-per-payload`).
        encoder.outputFormatting = .sortedKeys
        let data = try encoder.encode(payload)
        let encodedPayload = data.base64EncodedString().addingPercentEncoding(
            withAllowedCharacters: PairingInviteLink.queryValueAllowedCharacters
        ) ?? data.base64EncodedString()
        let prefix = "\(PairingInviteLink.scheme)://\(PairingInviteLink.host)"
        return "\(prefix)?\(PairingInviteLink.payloadQueryItem)=\(encodedPayload)"
    }

    static func pairingFields(from payload: PairingQRCodePayload) throws -> RemoteClientPairingFields {
        let validatedURL = try validatedRemoteURL(
            from: payload.apiURL,
            allowLocalhost: false,
            requireSecureTransportForRemote: true
        )
        let validatedSPKIPin = try resolvedSPKIPin(payload.spki, for: validatedURL)
        // A link with no project (a host with none open) is not refused here: pairing asks the host which it shares
        // (`sharing.ios-bad-library-path`).
        let libraryPath = normalizedLibraryPath(payload.libraryPath) ?? ""
        return RemoteClientPairingFields(
            remoteURL: validatedURL.absoluteString,
            pairCode: payload.pairCode,
            spkiPin: validatedSPKIPin,
            libraryPath: libraryPath,
            altURLs: payload.altURLs ?? []
        )
    }

    /// What an invite for `url` carries as its pin (#5891). `try? advertisableSPKIPin(...)` flattens the optional, so a
    /// publicly-trusted host (a `.ts.net` name behind `tailscale serve`), whose correct pin is nil, read as "no pin
    /// derived" and the host got no link at all.
    enum InvitePin: Equatable {
        /// The host's TLS is terminated by a public CA: the invite carries no pin.
        case notNeeded
        case pin(String)
        /// The host serves its own certificate and its pin is not known (yet) or not valid.
        case missing
    }

    static func invitePin(_ raw: String, for url: URL) -> InvitePin {
        // Never a link with no pin AND no TLS check: plain http is refused whatever the host (#5891).
        guard url.scheme?.lowercased() == "https" else { return .missing }
        do {
            if let pin = try advertisableSPKIPin(raw, for: url) { return .pin(pin) }
            return .notNeeded
        } catch {
            return .missing
        }
    }

    /// The pin a share surface should ADVERTISE for `url` — the mint-side twin
    /// of `resolvedSPKIPin`, so the two sides of a link agree by construction
    /// rather than by two surfaces remembering the same rule.
    ///
    /// Nil for a publicly-trusted host: there is nothing of ours to pin, and a
    /// link that named one would be asserting a key we do not hold. Throws when
    /// a host that serves its OWN certificate has no usable pin yet — the
    /// "still minting the certificate" state, which is a real blocker and must
    /// not quietly mint a pinless link for an engine that needs one (#5041).
    static func advertisableSPKIPin(_ raw: String, for url: URL) throws -> String? {
        guard !RemoteCertificatePinning.usesPublicCertificateAuthority(url: url) else { return nil }
        return try RemoteCertificatePinning.validatedSPKIPin(raw)
    }

    /// The pin this client should hold for `url`, from what the link advertised.
    ///
    /// A host that serves its own certificate MUST supply one — that is the only
    /// thing standing between the device and any machine answering to the same
    /// name, so an absent or malformed pin is still rejected. A host whose TLS a
    /// public CA terminates (`tailscale serve`) has no Fichero-held key to pin,
    /// so nil is the correct answer and any pin the link carried is discarded
    /// rather than trusted: it cannot describe the certificate that host
    /// presents (#5041).
    static func resolvedSPKIPin(_ advertised: String?, for url: URL) throws -> String? {
        guard !RemoteCertificatePinning.usesPublicCertificateAuthority(url: url) else { return nil }
        guard let advertised else { throw RemoteCertificatePinningError.missingSPKIPin }
        return try RemoteCertificatePinning.validatedSPKIPin(advertised)
    }

    private static func payloadFromInviteLink(_ message: String) -> PairingQRCodePayload? {
        guard let url = URL(string: message),
              isPairingInviteLink(url),
              let encodedPayload = queryValue(named: PairingInviteLink.payloadQueryItem, in: url),
              let data = Data(base64Encoded: encodedPayload),
              let payload = try? JSONDecoder.withISO8601Dates.decode(PairingQRCodePayload.self, from: data) else {
            return nil
        }
        return payload
    }

    private static func looksLikeInviteLink(_ message: String) -> Bool {
        guard let url = URL(string: message) else { return false }
        return isPairingInviteLink(url)
    }

    /// Whether `url` is a pairing invite in EITHER form — the custom
    /// `fichero://pair` scheme or the `https://fichero.app/pair` universal link
    /// (#3791). The app's `onOpenURL` handlers route on this so both forms reach
    /// the same pairing flow. Public within the target so `FicheroApp` can call it.
    static func isPairingInviteLink(_ url: URL) -> Bool {
        isCustomSchemeInvite(url) || isUniversalLinkInvite(url)
    }

    private static func isCustomSchemeInvite(_ url: URL) -> Bool {
        url.scheme?.lowercased() == PairingInviteLink.scheme
            && url.host?.lowercased() == PairingInviteLink.host
    }

    private static func isUniversalLinkInvite(_ url: URL) -> Bool {
        url.scheme?.lowercased() == PairingUniversalLink.scheme
            && url.host?.lowercased() == PairingUniversalLink.host
            && url.path.lowercased() == PairingUniversalLink.path
    }

    private static func queryValue(named name: String, in url: URL) -> String? {
        guard let query = url.query else { return nil }
        for pair in query.split(separator: "&") {
            let parts = pair.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard parts.count == 2, parts[0] == name else { continue }
            let rawValue = String(parts[1])
            return rawValue.removingPercentEncoding ?? rawValue
        }
        return nil
    }

    /// #3372: verify the paired credential can actually access `libraryPath`
    /// before it is persisted. A `nil`/empty advertised path (manual host entry,
    /// no library on the QR) has nothing to confirm — the library picker, which
    /// hits the same endpoint, gates access later. When a path IS advertised it
    /// must appear in the server's accessible-library set or pairing is rejected.
    @MainActor
    static func confirmLibraryAccess(
        libraryPath: String?,
        apiRoot: URL,
        expectedSPKIPin: String?
    ) async throws {
        guard normalizedLibraryPath(libraryPath) != nil else { return }
        let accessible = try await PairingService(apiRoot: apiRoot, expectedSPKIPin: expectedSPKIPin)
            .accessibleLibraryPaths()
        guard isLibraryConfirmed(advertised: libraryPath, in: accessible) else {
            throw RemoteClientPairingError.libraryPathNotConfirmed
        }
    }

    /// Pure decision: is the QR-advertised `advertised` library among the paths
    /// the server says this credential may access? A `nil`/empty advertised path
    /// is treated as "nothing to confirm" (true). Kept separate so the security
    /// decision is unit-testable without a live server (#3372).
    static func isLibraryConfirmed(advertised: String?, in accessible: [String]) -> Bool {
        guard let advertised = normalizedLibraryPath(advertised) else { return true }
        return accessible.contains { libraryPathsMatch($0, advertised) }
    }

    private static func libraryPathsMatch(_ lhs: String, _ rhs: String) -> Bool {
        // Lexically standardize (drops trailing slash, `.`/`..`), then compare
        // case-insensitively: the default macOS APFS volume is case-insensitive,
        // so `/Users/Alice/…` and `/Users/alice/…` are the same library — a
        // case-sensitive `==` would fail-closed-reject a legitimate pairing. The
        // check stays sound: paths differing only in case ARE the same file on
        // such a volume, so matching them is correct, not a weakening.
        func canonical(_ path: String) -> String {
            URL(fileURLWithPath: path.trimmingCharacters(in: .whitespacesAndNewlines))
                .standardizedFileURL.path
        }
        return canonical(lhs).compare(canonical(rhs), options: .caseInsensitive) == .orderedSame
    }

    @MainActor
    static func rollbackFailedHostSwitch(previousHost: String, attemptedHost: URL) {
        AuthTokenMiddleware.clearRemoteToken(hostString: attemptedHost.absoluteString)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: attemptedHost.absoluteString)
        DeviceTokenRenewal.clearExpiry(host: attemptedHost.absoluteString)
        EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
        EngineConfig.storeHost(previousHost)
    }

    /// Forgets the current pairing so a broken connection is no longer a dead
    /// end (#3971): undoes each value `persistPairedHost` wrote — the device
    /// token, the pinned certificate, the token expiry, the failover endpoint
    /// set, the configured host, and the paired library path. Clearing the
    /// paired-library-path key is what lets `EngineConfig.iosLaunchPhase` return
    /// `.setupNeeded` again, so the caller can drive the app back to the QR /
    /// pairing screen without a delete-and-reinstall.
    @MainActor
    static func forgetPairing() {
        let hostString = EngineConfig.hostString
        AuthTokenMiddleware.clearRemoteToken(hostString: hostString)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostString)
        DeviceTokenRenewal.clearExpiry(host: hostString)
        PairedHostEndpointStore.clear()
        EngineConfig.clearStoredHost()
        EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
    }

    /// Asks the Mac to revoke THIS device's pairing, with the device's own token, so the Mac stops listing it and the
    /// token stops working (`m2p.ios.forget-revokes-on-the-mac`, #6133). Best effort: false when the Mac cannot be reached
    /// or says no, and the caller forgets the pairing locally either way.
    @MainActor
    static func revokeOwnPairing() async -> Bool {
        let host = EngineConfig.host
        let pin = RemoteCertificatePinning.persistedSPKIPin(hostString: host.absoluteString)
        guard let client = try? FicheroClient(baseURL: host, expectedSPKIPin: pin) else { return false }
        return await revokeOwnPairing(client: client)
    }

    /// The call itself, over any client (a test hands one over a stubbed transport).
    /// Gives up after `timeout` seconds so an unreachable Mac cannot hold Forget This Mac for the transport's 60 s.
    @MainActor
    static func revokeOwnPairing(client: FicheroClient, timeout: Double = 5) async -> Bool {
        // A timer cancels the call, which then throws and reads as false; both stay on the main actor so the
        // non-Sendable client never crosses isolation.
        let call = Task { @MainActor () -> Bool in
            guard let response = try? await client.api.revokeOwnDeviceApiPairDevicesRevokeSelfPost(.init()) else { return false }
            if case .ok = response { return true }
            return false
        }
        let timer = Task {
            try? await Task.sleep(for: .seconds(timeout))
            call.cancel()
        }
        let revoked = await call.value
        timer.cancel()
        return revoked
    }

    static func normalizedLibraryPath(_ path: String?) -> String? {
        let trimmed = path?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty else { return nil }
        return trimmed
    }
}

private extension JSONDecoder {
    static var withISO8601Dates: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parseEngineDate(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Cannot decode QR payload date: \(raw)"
                )
            }
            return date
        }
        return decoder
    }
}
