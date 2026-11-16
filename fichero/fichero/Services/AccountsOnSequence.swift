import Foundation

/// `sharing.multiuser-off-says-so` (Step 3.3): turning accounts on in the engine's order, owner password first, so no later
/// step meets "404 multi-user auth is disabled". Pure: the engine calls sit behind `Host`, so the order is tested without one.
enum AccountsOnSequence {
    static let offSentence = "Accounts are off. Turn on accounts so other people can have their own sign-in."
    static let buttonTitle = "Turn on accounts…"
    static let createDisabledReason = "Turn on accounts first."
    static let anyoneElseNote = "Other people can sign in only on this Mac until Sharing is on."

    /// The one sentence under accounts being on while Sharing is off; nil when it does not apply.
    static func sharingNote(accountsOn: Bool, sharingOn: Bool) -> String? { accountsOn && !sharingOn ? anyoneElseNote : nil }

    /// A refusal from the engine, carrying only what the sentence needs.
    struct Refusal: Error, Equatable {
        let status: Int
        let detail: String?
    }

    enum Result: Equatable {
        case turnedOn
        /// The owner has not chosen a password: ask for one (a field, the 8-character rule), then run again with it.
        case needsPassword
        case failed(String)
    }

    @MainActor
    protocol Host {
        /// `multiuser_blocker` from `GET /api/pair/sharing`: non-nil says why accounts cannot be turned on yet.
        func blocker() async throws -> String?
        func setOwnerPassword(_ password: String) async throws
        func setMultiuser(_ enabled: Bool) async throws
        /// Re-reads the accounts and the switch, so Create Account follows what the engine now says.
        func reload() async
    }

    /// What to do next, from what the engine says and what the person has typed: ask for a password only when none was
    /// chosen and none has been typed. Pure, so the decision is tested without a host (#6565).
    static func needsPasswordPrompt(blocker: String?, typed: String?) -> Bool {
        typed == nil && blocker?.lowercased().contains("password") == true
    }

    /// The sentence for a refusal. A refusal that names the password after the person typed one is shown as words, never as
    /// another prompt (that was a silent loop), and a 403 carries the engine's own reason when it gave one.
    static func sentence(for refusal: Refusal) -> String {
        let said = (refusal.detail ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if refusal.status == 403, !said.isEmpty { return said }
        return PersonFacingError.message(for: refusal.status, detail: refusal.detail)
    }

    @MainActor
    static func run(host: some Host, password: String?) async -> Result {
        do {
            let blocker = try await host.blocker()
            if needsPasswordPrompt(blocker: blocker, typed: password) { return .needsPassword }
            if let password {
                guard password.count >= NewPasswordRule.minimumLength else { return .needsPassword }
                try await host.setOwnerPassword(password)
            }
            try await host.setMultiuser(true)
            await host.reload()
            return .turnedOn
        } catch let refusal as Refusal {
            if password == nil, refusal.status == 409, refusal.detail?.lowercased().contains("password") == true {
                return .needsPassword
            }
            return .failed(sentence(for: refusal))
        } catch {
            return .failed(error.localizedDescription)
        }
    }
}
