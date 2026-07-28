#if canImport(AppKit)
import CoreImage
import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import Foundation
import SwiftUI

extension ShareSettingsView {
    // MARK: - Pairing payload

    var hasValidSPKIPin: Bool {
        (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil
    }

    var validatedPublicURL: URL? {
        try? validatedHostedRemoteURL(from: publicBaseURL)
    }

    /// The advertised engine URL a QR/invite should point a phone at. NOT a
    /// service: minting a payload sends nothing, so it must not construct a
    /// client that would follow the app's own transport (#4224).
    var advertisedPairingRoot: URL? { validatedPublicURL }

    var pairingQRPayload: PairingQRCodePayload? {
        guard let pairingCode, let advertisedPairingRoot else { return nil }
        guard let normalizedPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else { return nil }
        return PairingService.buildQRCodePayload(
            apiRoot: advertisedPairingRoot,
            from: pairingCode,
            spki: normalizedPin,
            libraryPath: sharedLibraryPath
        )
    }

    var inviteLinkString: String? {
        guard let pairingQRPayload else { return nil }
        return try? RemoteClientPairing.inviteLinkString(from: pairingQRPayload)
    }

    var qrCodeImage: PlatformImage? {
        guard let pairingQRPayload else { return nil }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(pairingQRPayload) else { return nil }
        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 12, y: 12)),
              let cgImage = qrContext.createCGImage(output, from: output.extent) else { return nil }
        return PlatformImage(cgImage: cgImage, size: .zero)
    }

    func copyInvite() {
        guard let inviteLinkString else { return }
        PlatformPasteboard.writeString(inviteLinkString)
        copiedInvite = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            copiedInvite = false
        }
    }
}
#endif
