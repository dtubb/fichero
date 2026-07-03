import FicheroAPIClient
import SwiftUI

/// Sidebar badge showing a library's sharing state, with a members popover
/// (#2869 A4). Isolated in its own `View` so the type-check-sensitive
/// `LibrarySectionHeader.body` only pays for one extra expression — SwiftUI
/// type-checks each view body independently.
///
/// Renders nothing unless multi-user mode is on for this library, so the
/// default single-user experience is unchanged. Owner rows show a crown;
/// shared rows a two-person glyph. Tapping opens a popover that lists members
/// (roles joined with account names) from `GET /api/authz/members`.
struct LibrarySharingBadge: View {
    let library: LibraryManager.LibraryReference

    @State private var snapshot: Components.Schemas.LibraryAuthzSnapshot?
    @State private var members: [Components.Schemas.LibraryMember] = []
    @State private var showPopover = false
    @State private var isLoadingMembers = false
    @State private var membersError: String?
    @State private var isApplying = false
    @State private var manageError: String?

    private let sharingRoles = ["owner", "editor", "viewer"]

    var body: some View {
        Group {
            if let snapshot, snapshot.multiuserEnabled {
                Button {
                    showPopover = true
                } label: {
                    Image(systemName: iconName(for: snapshot))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help(helpText(for: snapshot))
                .accessibilityLabel(helpText(for: snapshot))
                .popover(isPresented: $showPopover, arrowEdge: .bottom) {
                    membersPopover
                }
                .task(id: showPopover) {
                    if showPopover { await loadMembers() }
                }
            }
        }
        .task(id: library.id) {
            await loadSnapshot()
        }
    }

    private func iconName(for snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        snapshot.currentUserRole == "owner" ? "crown" : "person.2"
    }

    private func helpText(for snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        if snapshot.currentUserRole == "owner" {
            return "Shared — you are the owner"
        }
        if let role = snapshot.currentUserRole {
            return "Shared — your role: \(role.capitalized)"
        }
        return "Shared library"
    }

    @ViewBuilder
    private var membersPopover: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Members")
                .font(.headline)

            if isLoadingMembers {
                ProgressView().controlSize(.small)
            } else if let membersError {
                Text(membersError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if members.isEmpty {
                Text("No one else has access yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(members, id: \.userId) { member in
                    memberRow(member)
                }
            }

            if let manageError {
                Text(manageError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .padding(12)
        .frame(width: 260)
    }

    @ViewBuilder
    private func memberRow(_ member: Components.Schemas.LibraryMember) -> some View {
        HStack(spacing: 8) {
            Image(systemName: member.isOwnerAccount ? "crown" : "person")
                .font(.caption)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text(member.displayName)
                Text("@\(member.username)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            // Owners manage roles inline (change / revoke). Your own row and
            // non-owner viewers just show the role — the engine enforces both.
            if canManage, member.userId != snapshot?.currentUserId {
                Menu(member.role.capitalized) {
                    ForEach(sharingRoles, id: \.self) { roleName in
                        Button(roleName.capitalized) {
                            Task { await changeRole(userId: member.userId, role: roleName) }
                        }
                    }
                    Divider()
                    Button("Remove", role: .destructive) {
                        Task { await revoke(userId: member.userId) }
                    }
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .disabled(isApplying)
            } else {
                Text(member.role.capitalized)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var canManage: Bool {
        snapshot?.canManageRoles == true
    }

    private func loadSnapshot() async {
        // Skip the network call entirely when multi-user is off — no badge,
        // no request in the common single-user case.
        guard EngineConfig.multiuserEnabled else {
            snapshot = nil
            return
        }
        snapshot = try? await library.actionsService.loadLibraryAuthzSnapshot()
    }

    private func loadMembers() async {
        isLoadingMembers = true
        membersError = nil
        defer { isLoadingMembers = false }
        do {
            members = try await library.actionsService.listLibraryMembers().members ?? []
        } catch {
            members = []
            membersError = error.localizedDescription
        }
    }

    private func changeRole(userId: String, role: String) async {
        await applyManagement {
            _ = try await library.actionsService.setLibraryRole(userId: userId, role: role)
        }
    }

    private func revoke(userId: String) async {
        await applyManagement {
            _ = try await library.actionsService.revokeLibraryRole(userId: userId)
        }
    }

    /// Run an owner-only ACL mutation, then refresh both the snapshot (your own
    /// manage rights may have changed) and the member list.
    private func applyManagement(_ mutate: () async throws -> Void) async {
        guard canManage else { return }
        isApplying = true
        manageError = nil
        defer { isApplying = false }
        do {
            try await mutate()
            await loadSnapshot()
            await loadMembers()
        } catch {
            manageError = error.localizedDescription
        }
    }
}
