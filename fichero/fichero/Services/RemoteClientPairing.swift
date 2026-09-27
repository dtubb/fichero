import FicheroAPIClient
import Foundation
#if canImport(UIKit)
import UIKit
#endif

struct RemoteClientPairingFields: Equatable {
    let remoteURL: String
    let pairCode: String
    /// Nil when the host's TLS is terminated by a public CA (#5041): there is
    /// no Fichero-held key to pin, and default trust evaluation is the check.
    let spkiPin: String?
    let libraryPath: String
}

enum RemoteClientPairingError: LocalizedError, Equatable {
    case missingPairCode
    case missingDeviceName
    case missingLibraryPath
    case invalidInviteLink
    case libraryPathNotConfirmed
    /// #5047: this app and the Mac were built from different API contracts, so
    /// the wire would be misread. Refuses rather than pairing into a connection
    /// that fails later in ways nobody could diagnose (design ruling 1). Carries
    /// the rendered mismatch so both versions reach the user.
    case contractMismatch(headline: String, detail: String)

    var errorDescription: String? {
        switch self {
        case .missingPairCode:
            return "Scan the pairing QR code or enter a pairing code."
        case .missingDeviceName:
            return "Enter a device name."
        case .missingLibraryPath:
            return "This QR code does not include a shared library. Show a new QR code on the Mac."
        case .invalidInviteLink:
            return "The invite link is incomplete or invalid."
        case .libraryPathNotConfirmed:
            return "The Mac did not confirm access to the library named in this QR code. "
                + "Show a fresh QR code on the Mac and scan it again."
        case .contractMismatch(let headline, let detail):
            return headline + ". " + detail
        }
    }
}
