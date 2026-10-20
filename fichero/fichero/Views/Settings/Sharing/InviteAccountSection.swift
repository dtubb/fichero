import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

// The hand-over of an invite link, shown after the Accounts `+` sheet mints one (`sharing.settings.accounts-add-sheet`).

/// Identifiable wrapper so a freshly-minted invite can drive a `.sheet(item:)`
/// (the generated `InviteMintResponse` isn't `Identifiable`).
struct MintedInvite: Identifiable {
    let id = UUID()
    let mint: Components.Schemas.InviteMintResponse
}

/// The hand-over sheet: shows the redemption link and its QR (reusing the same
/// `CIFilter.qrCodeGenerator` presentation as device pairing) for the owner to
/// pass to the invitee.
struct InviteLinkSheet: View {
    let mint: Components.Schemas.InviteMintResponse

    @Environment(\.dismiss) private var dismiss
    @State private var copied = false

    private var displayName: String {
        mint.invite.displayName.isEmpty ? mint.invite.username : mint.invite.displayName
    }

    var body: some View {
        VStack(spacing: 16) {
            VStack(spacing: 4) {
                Text("Invite \(displayName)")
                    .font(.title2)
                    .fontWeight(.semibold)
                Text("Send this link. They open it in Fichero and set their own password.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            if let qrImage = Self.qrImage(from: mint.redemptionUrl) {
                Image(platformImage: qrImage)
                    .interpolation(.none)
                    .resizable()
                    .frame(width: 200, height: 200)
                    .accessibilityLabel("Invite QR code")
            }

            Text(mint.redemptionUrl)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .lineLimit(2)
                .truncationMode(.middle)
                .frame(maxWidth: 320)

            Text("This invite expires \(mint.invite.expiresAt.formatted(.relative(presentation: .named))).")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack {
                Button {
                    PlatformPasteboard.writeString(mint.redemptionUrl)
                    copied = true
                } label: {
                    Label(copied ? "Copied" : "Copy Link", systemImage: copied ? "checkmark" : "doc.on.doc")
                }
                .buttonStyle(.bordered)

                Button("Done") { dismiss() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(28)
        .frame(minWidth: 320)
    }

    /// QR image for the redemption URL. Cross-platform: `NSImage`/`UIImage` via
    /// the `PlatformImage` alias.
    private static func qrImage(from string: String) -> PlatformImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 12, y: 12)),
              let cgImage = CIContext().createCGImage(output, from: output.extent) else { return nil }
        #if canImport(AppKit)
        return PlatformImage(cgImage: cgImage, size: .zero)
        #else
        return PlatformImage(cgImage: cgImage)
        #endif
    }
}
