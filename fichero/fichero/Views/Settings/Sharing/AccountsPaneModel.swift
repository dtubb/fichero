import Foundation

/// What Settings › Accounts lists and what its `+` sheet asks (`sharing.settings.three-panes`,
/// `sharing.settings.accounts-add-sheet`, #5928): the words and the rules, apart from the view, so they are tested without a window.
enum AccountsPaneModel {
    struct Person: Equatable {
        let id: String
        let name: String
        let username: String
        let isOwner: Bool
        let isActive: Bool
    }

    struct Invitation: Equatable {
        let id: String
        let name: String
        let username: String
    }

    struct Row: Identifiable, Equatable {
        enum Kind: Equatable { case person, invited }
        let id: String
        let kind: Kind
        /// The name, or the username when there is no name.
        let title: String
        let username: String
        /// "Owner", or nothing for anyone else; an invited row says "Invited" and nothing else.
        let role: String
        /// The You mark replaces the old "Signed In As" section.
        let isYou: Bool
        let isActive: Bool

        /// What − does to this row when it is selected: an invite is revoked, a person (never you) disabled or enabled.
        var removeAction: String? {
            switch kind {
            case .invited: "Revoke"
            case .person: isYou ? nil : (isActive ? "Disable" : "Enable")
            }
        }
    }

    /// You first, then owners, then the rest by name; pending invites last, in grey.
    static func rows(people: [Person], currentID: String?, invitations: [Invitation]) -> [Row] {
        let persons = people.map { person in
            Row(id: person.id, kind: .person, title: person.name.isEmpty ? person.username : person.name,
                username: person.username, role: person.isOwner ? "Owner" : "", isYou: person.id == currentID,
                isActive: person.isActive)
        }
        .sorted { lhs, rhs in
            if lhs.isYou != rhs.isYou { return lhs.isYou }
            if (lhs.role == "Owner") != (rhs.role == "Owner") { return lhs.role == "Owner" }
            return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
        }
        let invited = invitations.map {
            Row(id: "invite:\($0.id)", kind: .invited, title: $0.name.isEmpty ? $0.username : $0.name, username: $0.username,
                role: "Invited", isYou: false, isActive: true)
        }
        return persons + invited
    }
}

/// The `+` sheet: Full name, Username, then Password or Send invite link, and Owner (off).
enum AccountsAddSheetModel {
    enum Way: CaseIterable, Equatable { case password, invite }

    /// A new account's password rule, the same the invite redeem applies.
    static let minimumPasswordLength = 8

    /// The invite choice is there only while Multi-user is on: an invite is meaningless without it.
    static func offersInvite(multiUserOn: Bool) -> Bool { multiUserOn }

    /// Owner is for an account made with a password; an invited person starts as a viewer and sets their own password.
    static func asksOwner(way: Way) -> Bool { way == .password }

    static func buttonTitle(way: Way, isWorking: Bool) -> String {
        if isWorking { return way == .password ? "Creating…" : "Sending…" }
        return way == .password ? "Create Account" : "Send Invite Link"
    }

    /// The one line under the fields when what is typed cannot be sent yet: nothing until something is typed.
    static func problem(name: String, username: String, way: Way, password: String) -> String? {
        if name.trimmed.isEmpty != username.trimmed.isEmpty { return "Enter a name and a username" }
        if way == .password, !password.isEmpty, password.count < minimumPasswordLength {
            return "Use at least \(minimumPasswordLength) characters for the password"
        }
        return nil
    }

    static func canSubmit(name: String, username: String, way: Way, password: String, isWorking: Bool) -> Bool {
        guard !isWorking, !name.trimmed.isEmpty, !username.trimmed.isEmpty else { return false }
        return way == .invite || password.count >= minimumPasswordLength
    }

    /// The engine's words, one line; a taken username is said plainly. Nothing internal is added or shown.
    static func failureWords(_ message: String) -> String {
        let text = message.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.localizedCaseInsensitiveContains("already exists") || text.localizedCaseInsensitiveContains("taken") {
            return "That username is taken"
        }
        return text.isEmpty ? "Couldn't add the account" : text
    }
}

private extension String {
    var trimmed: String { trimmingCharacters(in: .whitespaces) }
}
