import CoreImage.CIFilterBuiltins
import FicheroAPIClient
import SwiftUI

/// Owner-side account-invite UI (#3157). Mints a `fichero://invite` link the
/// owner hands to a new person, and lists/revokes pending invites. Wired to the
/// invite endpoints the backend shipped in #3153 through `UsersStore` — no
/// direct client calls from the view.
struct InviteAccountSection: View {
    let store: UsersStore

    @State private var newUsername = ""
    @State private var newDisplayName = ""
    @State private var isMinting = false
    @State private var errorMessage: String?
    @State private var minted: MintedInvite?

    private var canInvite: Bool {
        !newUsername.trimmingCharacters(in: .whitespaces).isEmpty && !isMinting
    }

    var body: some View {
        Group {
            Section {
                TextField("Username", text: $newUsername)
                    .textContentType(.username)
                    #if !os(macOS)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    #endif
                TextField("Full name (optional)", text: $newDisplayName)
                    .textContentType(.name)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                Button {
                    Task { await mint() }
                } label: {
                    if isMinting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Invite Person…")
                    }
                }
                .disabled(!canInvite)
            } header: {
                Text("Invite a Person")
            } footer: {
                Text("Creates an invite link to hand over. They open it and set their own password to join.")
                    .foregroundStyle(.secondary)
            }

            if !store.invites.isEmpty {
                Section("Pending Invites") {
                    ForEach(store.invites, id: \.id) { invite in
                        inviteRow(invite)
                    }
                }
            }
        }
        .sheet(item: $minted) { wrapper in
            InviteLinkSheet(mint: wrapper.mint)
        }
    }

    @ViewBuilder
    private func inviteRow(_ invite: Components.Schemas.InviteResponse) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(invite.displayName.isEmpty ? invite.username : invite.displayName)
                    .fontWeight(.medium)
                Text("@\(invite.username) · expires \(invite.expiresAt.formatted(.relative(presentation: .named)))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Revoke") {
                Task { await revoke(invite.id) }
            }
            .buttonStyle(.borderless)
            .foregroundStyle(.red)
            .disabled(isMinting)
        }
        .padding(.vertical, 2)
    }

    @MainActor
    private func mint() async {
        isMinting = true
        errorMessage = nil
        defer { isMinting = false }
        do {
            let mint = try await store.createInvite(
                username: newUsername.trimmingCharacters(in: .whitespaces),
                displayName: newDisplayName.trimmingCharacters(in: .whitespaces).isEmpty
                    ? nil : newDisplayName.trimmingCharacters(in: .whitespaces)
            )
            newUsername = ""
            newDisplayName = ""
            minted = MintedInvite(mint: mint)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    private func revoke(_ id: String) async {
        isMinting = true
        errorMessage = nil
        defer { isMinting = false }
        do {
            try await store.revokeInvite(id: id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Identifiable wrapper so a freshly-minted invite can drive a `.sheet(item:)`
/// (the generated `InviteMintResponse` isn't `Identifiable`).
private struct MintedInvite: Identifiable {
    let id = UUID()
    let mint: Components.Schemas.InviteMintResponse
}

/// The hand-over sheet: shows the redemption link and its QR (reusing the same
/// `CIFilter.qrCodeGenerator` presentation as device pairing) for the owner to
/// pass to the invitee.
private struct InviteLinkSheet: View {
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
