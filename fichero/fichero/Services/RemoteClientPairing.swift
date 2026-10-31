import FicheroAPIClient
import Foundation

struct RemoteClientPairingFields: Equatable {
    let remoteURL: String
    let pairCode: String
    /// Nil when the host's TLS is terminated by a public CA (#5041): there is
    /// no Fichero-held key to pin, and default trust evaluation is the check.
    let spkiPin: String?
    let libraryPath: String
}

/// The person a pairing device signs in as when the host has Multi-user on.
struct PairingPerson: Equatable {
    let username: String
    let password: String

    /// Nil unless both fields are filled, so a half-typed picker never sends a partial person.
    init?(username: String, password: String) {
        let name = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, !password.isEmpty else { return nil }
        self.username = name
        self.password = password
    }

    /// The engine's answer to a no-person pairing while Multi-user is on (401, "person required: ...").
    static func isRequiredRefusal(status: Int, detail: String?) -> Bool {
        status == 401 && (detail ?? "").hasPrefix("person required")
    }
}

enum RemoteClientPairingError: LocalizedError, Equatable {
    case missingPairCode
    case missingDeviceName
    case missingLibraryPath
    case invalidInviteLink
    case libraryPathNotConfirmed
    /// The host uses Multi-user: the device must say which person it is (`sharing.device-chooses-person`).
    case personRequired
    /// #5047: this app and the Mac were built from different API contracts, so
    /// the wire would be misread. Refuses rather than pairing into a connection
    /// that fails later in ways nobody could diagnose (design ruling 1). Carries
    /// the rendered mismatch so both versions reach the user.
    case contractMismatch(headline: String, detail: String)
    /// The host answered and made the device, but this device could not keep the key (a Keychain refusal: on the DMG
    /// builds before 2026-10-31, errSecMissingEntitlement). The device was revoked on the host again and nothing was
    /// paired (`sharing.failed-save-spends-nothing`); the OSStatus goes to the log, never to the person.
    case tokenNotSaved

    /// The noun for the device the sentence is about: "Mac" on a Mac, "device" on iPhone and iPad. Not the idiom
    /// (`UIDevice.current` is main-actor isolated and `LocalizedError` is read from any context, review S-H1): the
    /// Connect sheets, which know the idiom, may say more.
    static var deviceNoun: String {
        #if os(macOS)
        return "Mac"
        #else
        return "device"
        #endif
    }

    /// "This Mac" / "This device": the sentence's subject, capitalised.
    static var thisDevice: String { "This \(deviceNoun)" }

    var errorDescription: String? {
        switch self {
        case .tokenNotSaved:
            return "\(Self.thisDevice) couldn't save the connection key in its Keychain, so nothing was paired. "
                + "Update Fichero on this \(Self.deviceNoun) and ask for a new link."
        case .missingPairCode:
            #if os(macOS)
            return "Paste the invite link from the host Mac."
            #else
            return "Scan the pairing QR code or enter a pairing code."
            #endif
        case .missingDeviceName:
            return "Enter a device name."
        case .missingLibraryPath:
            #if os(macOS)
            return "This invite link does not include a shared project. Copy a new one on the host Mac."
            #else
            return "This QR code does not include a shared project. Show a new QR code on the Mac."
            #endif
        case .invalidInviteLink:
            return "The invite link is incomplete or invalid."
        case .libraryPathNotConfirmed:
            #if os(macOS)
            return "The host Mac did not confirm access to the project named in this invite link. "
                + "Copy a fresh invite link on the host Mac and paste it again."
            #else
            return "The Mac did not confirm access to the project named in this QR code. "
                + "Show a fresh QR code on the Mac and scan it again."
            #endif
        case .personRequired:
            return "This library uses Multi-user. Enter the username and password you sign in with."
        case .contractMismatch(let headline, let detail):
            return headline + ". " + detail
        }
    }
}
