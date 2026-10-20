import Foundation

/// The guest half of `sharing.synced-device-pairs-by-host-code` (#5898): a synced project opened on a Mac that holds no
/// token for its host asks, once, for the host's pairing LINK. The copy carries only the host's address and which person
/// (never a token); trust comes from the link, never from a bare code.
struct SyncedHostRecord: Codable, Equatable {
    /// Written into the project's root beside the copy; the host Mac writes it (bugs' half of #5898).
    static let fileName = "sharing-host.json"

    let hostURL: String
    let hostName: String
    let person: String
}

enum SyncedHostAsk {
    /// Whether to ask now: the copy names a host, this Mac holds no token for it, and the ask was not dismissed.
    static func needsAsk(_ record: SyncedHostRecord?, hasToken: (String) -> Bool, dismissed: Bool) -> Bool {
        guard let record, !dismissed else { return false }
        return !hasToken(record.hostURL)
    }

    static func sentence(_ record: SyncedHostRecord) -> String {
        "This project is hosted on \(record.hostName). Ask \(record.person) for a pairing link."
    }

    static let readOnlyNote = "Until you connect, this project opens read-only from the copy on this Mac."

    /// The fields to redeem, from a pasted LINK for this record's host. A bare code, a link for another Mac, or anything
    /// else is refused in words.
    static func fields(fromLink text: String, record: SyncedHostRecord) throws -> RemoteClientPairingFields {
        let pasted = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard URL(string: pasted).map(RemoteClientPairing.isPairingInviteLink) == true else {
            throw SyncedHostAskError.notALink
        }
        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: pasted)
        let host = HostChoices.Found(name: record.hostName, publicURL: record.hostURL)
        guard HostChoices.invite(fields.remoteURL, isFor: host) else {
            throw SyncedHostAskError.otherHost(record.hostName)
        }
        return fields
    }

    /// The host's refusal, in words: which of wrong / used / expired the engine told (`POST /api/pair`).
    static func words(forStatus status: Int, detail: String?) -> String {
        switch (status, (detail ?? "").lowercased()) {
        case (401, let d) where d.contains("invalid or expired"):
            return "That link was already used, has expired, or is not the host's. Ask for a new one."
        case (401, let d) where d.hasPrefix("person required"):
            return "The host needs to know who you are. Ask them for a link made for you."
        case (400, let d) where d.contains("https"):
            return "The host is not reachable securely, so it will not pair."
        case (429, _):
            return "Too many tries. Wait a minute and paste the link again."
        default:
            return "The host did not accept the link (\(status)). Ask for a new one."
        }
    }

    static func read(in libraryRoot: URL) -> SyncedHostRecord? {
        (try? Data(contentsOf: libraryRoot.appendingPathComponent(SyncedHostRecord.fileName)))
            .flatMap { try? JSONDecoder().decode(SyncedHostRecord.self, from: $0) }
    }

    private static func key(_ root: URL) -> String { "sharing.hostAskDismissed." + root.path }

    static func isDismissed(_ root: URL, defaults: UserDefaults = .standard) -> Bool { defaults.bool(forKey: key(root)) }

    static func dismiss(_ root: URL, defaults: UserDefaults = .standard) { defaults.set(true, forKey: key(root)) }
}

enum SyncedHostAskError: LocalizedError, Equatable {
    case notALink
    case otherHost(String)

    var errorDescription: String? {
        switch self {
        case .notALink: "Paste the whole pairing link, not just a code."
        case .otherHost(let name): "That link is for another Mac than \(name). Ask \(name) for a link."
        }
    }
}
