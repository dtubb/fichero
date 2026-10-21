import FicheroAPIClient
import SwiftUI

/// Settings › Sharing: the invitations that have not been used, each with Revoke (`sharing.invite.revoke`). A revoked link stops
/// working at once.
struct PendingInvitesSection: View {
    @State private var store: PairInvitesStore

    init(store: PairInvitesStore = PairInvitesStore(service: PairingService(apiRoot: EngineConfig.host))) {
        _store = State(initialValue: store)
    }

    var body: some View {
        Section("Invitations") {
            if store.invites.isEmpty {
                Text("No invitations waiting.").foregroundStyle(.secondary)
            }
            ForEach(store.invites, id: \.id) { invite in
                HStack {
                    VStack(alignment: .leading) {
                        Text(invite.person)
                        Text(PendingInviteText.detail(role: invite.role, expiresAt: invite.expiresAt))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Revoke", role: .destructive) { Task { await store.revoke(invite) } }
                        .accessibilityIdentifier("sharing.invites.revoke")
                }
            }
            if let message = store.errorMessage {
                Label(message, systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.orange)
            }
        }
        .task { await store.load() }
    }
}

#Preview {
    Form {
        PendingInvitesSection(store: PairInvitesStore(
            list: { [.init(id: "i1", person: "ana", newPerson: false, role: "editor", mintedBy: "owner")] },
            revoke: { _ in }))
    }
    .formStyle(.grouped)
}
