import Foundation

/// The sentence beside the Multi-user switch when the engine refuses (`sharing.multiuser-switch-says-the-refusal`, #6299):
/// the engine's own `detail` where it has one, never "Unexpected response" and never a bare status. The 2026-10-31 400
/// ("Missing X-Fichero-Library-Path header") reached the person as "Unexpected response"; the 409 password gap and the
/// 403 are the designed refusals (#5908) and read as the next step.
enum MultiuserSwitchWords {
    static let passwordFirst = "Choose a password for your account first, then turn Multi-user on."
    static let ownerOnly = "Sign in as the owner to change Multi-user."

    static func sentence(status: Int, detail: String?) -> String {
        let trimmed = detail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        switch status {
        case 409 where trimmed.lowercased().contains("password"):
            return passwordFirst
        case 403:
            return ownerOnly
        default:
            if !trimmed.isEmpty { return trimmed }
            return "Fichero's server refused the change (\(status)). Try again, and if it keeps happening quit and reopen Fichero."
        }
    }
}
