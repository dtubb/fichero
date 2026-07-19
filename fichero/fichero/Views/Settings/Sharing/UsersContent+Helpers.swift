import FicheroAPIClient
import SwiftUI

// MARK: - Helpers & Utilities

extension UsersContent {
    /// Every library keeps at least one owner. Say WHY the control is unavailable —
    /// a disabled button with no explanation is a dead control.
    internal func lastOwnerExplanation(isSoleOwner: Bool) -> String {
        if isSoleOwner {
            return "You're the only owner, so you can't remove or downgrade your own access — "
                + "the library would be left with nobody who can administer it. "
                + "Give someone else the Owner role first, then they can change yours."
        }
        return "You can't remove your own access. Another owner can do it for you."
    }

    /// True when this row is the library's last remaining owner. Read from the
    /// engine's own ACL snapshot — the engine stays the enforcer.
    internal func isSoleOwner(_ role: Components.Schemas.LibraryRole) -> Bool {
        guard role.role.lowercased() == "owner" else { return false }
        return (authzSnapshot?.roles ?? []).filter { $0.role.lowercased() == "owner" }.count == 1
    }

    internal func user(for userId: String) -> Components.Schemas.UserResponse? {
        allUsers.first(where: { $0.id == userId })
    }

    internal var allUsers: [Components.Schemas.UserResponse] {
        var seen = Set<String>()
        return ([store.currentUser] + store.users).compactMap { $0 }.filter { user in
            seen.insert(user.id).inserted
        }
    }

    internal var sortedRoles: [Components.Schemas.LibraryRole] {
        (authzSnapshot?.roles ?? []).sorted { lhs, rhs in
            let lhsRank = roleRank(lhs.role)
            let rhsRank = roleRank(rhs.role)
            if lhsRank != rhsRank { return lhsRank < rhsRank }
            return displayName(for: user(for: lhs.userId) ?? placeholderUser(lhs.userId))
                < displayName(for: user(for: rhs.userId) ?? placeholderUser(rhs.userId))
        }
    }

    internal var unassignedUsers: [Components.Schemas.UserResponse] {
        let assignedIds = Set((authzSnapshot?.roles ?? []).map { $0.userId })
        return allUsers.filter { !assignedIds.contains($0.id) }
    }

    internal func roleRank(_ role: String) -> Int {
        switch role.lowercased() {
        case "owner":
            return 0
        case "editor":
            return 1
        default:
            return 2
        }
    }

    internal func isRoleEditable() -> Bool {
        authzSnapshot?.canManageRoles == true
    }

    internal func targetAccessText(_ snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        if snapshot.targetCanWrite { return "Read / Write" }
        if snapshot.targetCanRead { return "Read only" }
        return "Blocked"
    }

    internal func authzStatusText(_ isOn: Bool) -> some View {
        Text(isOn ? "Enabled" : "Disabled")
            .foregroundStyle(isOn ? Color.accentColor : .secondary)
    }

    internal func displayName(for user: Components.Schemas.UserResponse) -> String {
        user.displayName.isEmpty ? user.username : user.displayName
    }

    internal func placeholderUser(_ userId: String) -> Components.Schemas.UserResponse {
        .init(
            id: userId,
            username: userId,
            displayName: userId,
            isOwner: false,
            active: true,
            createdAt: .now
        )
    }
}
