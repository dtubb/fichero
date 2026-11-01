#if canImport(AppKit)
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import Foundation
import SwiftUI

extension ShareSettingsView {
    // MARK: - Pairing payload

    /// True once this address has whatever credential it actually needs: a
    /// valid pin for an engine serving its own certificate, nothing at all for
    /// a publicly-trusted one (#5041).
    var hasValidSPKIPin: Bool {
        guard let url = validatedPublicURL else { return false }
        return RemoteClientPairing.invitePin(spkiPin, for: url) != .missing
    }

    var validatedPublicURL: URL? {
        try? validatedHostedRemoteURL(from: publicBaseURL)
    }

    /// The advertised engine URL a QR/invite should point a phone at. NOT a
    /// service: minting a payload sends nothing, so it must not construct a
    /// client that would follow the app's own transport (#4224).
    var advertisedPairingRoot: URL? {
        AddressChoiceModel.root(for: addressChoice, rows: addressRows) ?? validatedPublicURL
    }

    /// The addresses the sheet offers (`sharing.share-sheet-offers-both-addresses`): the sharing address and the tailnet
    /// address the engine reports, each with its reach and, when it cannot work, why.
    var addressRows: [AddressRow] {
        AddressChoiceModel.rows(sharingAddress: publicBaseURL,
                                tailnetURL: sharingState?.tailnetURL ?? detectedTailnetURL,
                                tailnetForward: sharingState?.tailnetForward)
    }

    /// The link for one row (its own Copy), built from the same code as the QR.
    func inviteLinkString(for choice: AddressChoice) -> String? {
        guard let pairingCode, let root = AddressChoiceModel.root(for: choice, rows: addressRows) else { return nil }
        let advertisedPin: String?
        switch RemoteClientPairing.invitePin(spkiPin, for: root) {
        case .missing: return nil
        case .notNeeded: advertisedPin = nil
        case .pin(let pin): advertisedPin = pin
        }
        let payload = PairingService.buildQRCodePayload(
            apiRoot: root, from: pairingCode, spki: advertisedPin, libraryPath: sharedLibraryPath)
        return try? RemoteClientPairing.inviteLinkString(from: payload)
    }

    func copyInvite(for choice: AddressChoice) {
        let outcome = PairingLinkCopy.attempt(
            link: inviteLinkString(for: choice), blocker: pairingBlocker,
            write: PlatformPasteboard.writeString, read: PlatformPasteboard.string)
        switch outcome {
        case .copied: copyNote = nil
        case .notCopied(let reason): copyNote = reason
        }
    }

    var pairingQRPayload: PairingQRCodePayload? {
        guard let pairingCode, let advertisedPairingRoot else { return nil }
        let advertisedPin: String?
        switch RemoteClientPairing.invitePin(spkiPin, for: advertisedPairingRoot) {
        case .missing: return nil
        case .notNeeded: advertisedPin = nil  // a publicly-trusted host: the link carries no pin (#5891)
        case .pin(let pin): advertisedPin = pin
        }
        return PairingService.buildQRCodePayload(
            apiRoot: advertisedPairingRoot,
            from: pairingCode,
            spki: advertisedPin,
            libraryPath: sharedLibraryPath
        )
    }

    var inviteLinkString: String? {
        guard let pairingQRPayload else { return nil }
        return try? RemoteClientPairing.inviteLinkString(from: pairingQRPayload)
    }

    /// Draws the QR for the current payload; called once per link by the view's task, never from the body.
    func makeQRCodeImage() -> PlatformImage? {
        guard let pairingQRPayload else { return nil }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = .sortedKeys  // the same bytes as the copied link (`sharing.qr-drawn-once-per-payload`)
        guard let data = try? encoder.encode(pairingQRPayload) else { return nil }
        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 12, y: 12)),
              let cgImage = qrContext.createCGImage(output, from: output.extent) else { return nil }
        return PlatformImage(cgImage: cgImage, size: .zero)
    }

    func copyInvite() {
        let outcome = PairingLinkCopy.attempt(
            link: inviteLinkString, blocker: pairingBlocker,
            write: PlatformPasteboard.writeString, read: PlatformPasteboard.string)
        switch outcome {
        case .copied:
            copyNote = nil
            copiedInvite = true
            Task {
                try? await Task.sleep(for: .seconds(2))
                copiedInvite = false
            }
        case .notCopied(let reason):
            copiedInvite = false
            copyNote = reason
        }
    }
}
#endif
