import Foundation

/// A Mac and a phone pair through ONE sequence (`sharing.both-clients-run-the-same-checks`, `sharing.ios-bad-library-path`):
/// try the link's addresses (health, which also reads the contract) → refuse a contract this app cannot read, before any code is
/// sent → `POST /api/pair` → confirm the library from `GET /api/authz/libraries`, or, when the link names none, list the host's
/// and let the person choose (never "missing library" before the network). The two entry points differ only in what they do with
/// the result (the Mac switches its engine host, the phone stores the host), so they cannot drift.
enum PairingSequence {
    struct Link: Equatable {
        var addresses: [String]
        var code: String
        /// nil: the link names no library (a host with no project open); the sequence lists the host's.
        var libraryPath: String?
    }

    struct HostHealth: Equatable {
        var contract: String?
        var version: String?
    }

    /// What the sequence needs from a host. A test implements it with one fake host and reads its ordered call log.
    protocol Host: Sendable {
        /// nil when the address answered; the failure otherwise. Called once per address, in order.
        func health(at url: String) async -> (failure: PairingFailure?, health: HostHealth?)
        /// Redeems the code at the address that answered. Throws a failure the sheet can say.
        func pair(at url: String, code: String) async throws
        /// The library paths this device may use on the host (`GET /api/authz/libraries`).
        func libraries(at url: String) async throws -> [String]
        /// Undo the pairing when a later step refuses (the token kept so the library call could be made is cleared).
        func discardPairing(at url: String) async
    }

    enum Result: Equatable {
        /// Something else stopped it, already in words (a thrown error that carries its own sentence, e.g. the Keychain refusal).
        case stopped(message: String)
        case paired(url: String, libraryPath: String)
        /// The link named no library and the host has several: the person picks one, nothing is persisted yet.
        case choose(url: String, libraries: [String])
        case failed(PairingFailure, context: PairingFailure.Context)
    }

    static func run(link: Link, host: some Host, ownContract: String, ownVersion: String? = nil,
                    sleep: @escaping @Sendable (Double) async -> Void = PairingAddressTry.realSleep) async -> Result {
        let seen = HealthBox()
        let tried = await PairingAddressTry.run(addresses: link.addresses, sleep: sleep) { url in
            let answer = await host.health(at: url)
            if answer.failure == nil { await seen.set(answer.health) }
            return answer.failure
        }
        guard let url = tried.chosen else {
            let name = PairingAddressTry.host(link.addresses.first ?? "")
            return .failed(tried.attempts.last?.failure ?? .noAnswer, context: .init(host: name))
        }
        let answered = await seen.value
        let context = PairingFailure.Context(host: PairingAddressTry.host(url), hostVersion: answered?.version, thisVersion: ownVersion)
        if let hostContract = answered?.contract, hostContract != ownContract {
            return .failed(.versionMismatch, context: context)  // refused before any code is sent
        }
        do {
            try await host.pair(at: url, code: link.code)
            let libraries = try await host.libraries(at: url)
            if let named = link.libraryPath {
                if libraries.contains(named) { return .paired(url: url, libraryPath: named) }
                await host.discardPairing(at: url)
                return .failed(.libraryNotGiven, context: context)
            }
            switch libraries.count {
            case 0:
                await host.discardPairing(at: url)
                return .failed(.libraryNotGiven, context: context)
            case 1: return .paired(url: url, libraryPath: libraries[0])
            default: return .choose(url: url, libraries: libraries)
            }
        } catch let failure as PairingFailure {
            await host.discardPairing(at: url)
            return .failed(failure, context: context)
        } catch {
            await host.discardPairing(at: url)
            return .stopped(message: (error as? LocalizedError)?.errorDescription ?? "Fichero couldn't do that. Try again.")
        }
    }

    private actor HealthBox {
        private(set) var value: HostHealth?
        func set(_ health: HostHealth?) { value = health }
    }
}
