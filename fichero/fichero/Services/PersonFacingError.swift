import Foundation

/// The one place an engine refusal becomes a sentence a person reads (`sharing.undocumented-never-reaches-the-person`).
/// No generated-client `.undocumented(statusCode:payload)` value and no `"\(response)"` interpolation is ever shown:
/// `scripts/check_swift_transport.py` fails a Swift file that does it, and each new site uses this.
enum PersonFacingError {
    struct Context: Equatable {
        /// What the person can do about a 404 here, appended to "That isn't available on this Mac right now."
        var fix: String?
        /// The surface is gated by Multi-user (Create Account, invitations): a 404 there means accounts are off.
        var accountsOff = false
    }

    static let accountsOffSentence = "Accounts are off. Turn on accounts first."

    /// `detail` is the engine's own words when the body was the framework's `{"detail": "..."}`.
    static func message(for status: Int, detail: String? = nil, context: Context = Context()) -> String {
        let said = (detail ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if said.lowercased().contains("multi-user auth is disabled") || (context.accountsOff && [404, 409].contains(status)) {
            return accountsOffSentence
        }
        switch status {
        case 401: return "Sign in again."
        case 403: return "You don't have permission to do that."
        case 404:
            let base = "That isn't available on this Mac right now."
            return context.fix.map { "\(base) \($0)" } ?? base
        case 409: return said.isEmpty ? "Fichero couldn't do that right now. Try again." : said
        case 422: return said.isEmpty ? "Something in that request wasn't valid." : said
        case 429: return "Too many tries, wait a minute."
        case 500...599:
            return "Fichero's server had a problem; try again, and if it keeps happening quit and reopen Fichero."
        default: return said.isEmpty ? "Fichero couldn't do that. Try again." : said
        }
    }

    /// The same for a generated response enum, without printing it: the status is read from the case itself (`.undocumented`
    /// carries it; the documented refusals are named for theirs). The body is not read here (it streams), so the engine's
    /// own `detail` is the caller's to pass to `message(for:detail:context:)` when it has it.
    static func message(forResponse response: Any, context: Context = Context()) -> String {
        message(for: status(of: response) ?? 0, context: context)
    }

    static func status(of response: Any) -> Int? {
        // The case's name is only looked up here (a case with no payload has no Mirror children); it is never shown.
        let label = String(describing: response).prefix { $0 != "(" }
        if label == "undocumented" {
            let payload = Mirror(reflecting: response).children.first?.value
            return payload.flatMap { Mirror(reflecting: $0).children.first { $0.label == "statusCode" }?.value as? Int }
                ?? payload.flatMap { Mirror(reflecting: $0).children.first?.value as? Int }
        }
        let named: [String: Int] = [
            "unauthorized": 401, "forbidden": 403, "notFound": 404, "conflict": 409,
            "unprocessableContent": 422, "tooManyRequests": 429
        ]
        return named[String(label)]
    }
}
