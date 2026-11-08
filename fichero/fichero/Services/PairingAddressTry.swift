import Foundation

/// Pairing and reconnecting try a link's addresses one after another, in the link's order, each within 5 seconds, and stop at the
/// first that answers (`sharing.client-tries-every-address`). Sequential, not a race: a race hides which address failed and why,
/// and three addresses cost at most 15 seconds. The attempt is the unauthenticated health call, so the pin and name check (TLS) and
/// the version check happen on the address that answered, before any code is sent.
enum PairingAddressTry {
    static let budgetSeconds: Double = 5
    static let maxAddresses = 3

    struct Attempt: Equatable {
        let url: String
        /// nil: this address answered.
        let failure: PairingFailure?
    }

    struct Outcome: Equatable {
        let attempts: [Attempt]
        /// The first address that answered, nil when none did.
        var chosen: String? { attempts.first { $0.failure == nil }?.url }

        /// What the person reads: which address connected and why each earlier one did not, or every attempt when none did.
        var sentence: String {
            guard let chosen else {
                let first = PairingAddressTry.host(attempts.first?.url ?? "")
                let tried = attempts.map { "\(PairingAddressTry.label($0.url)): \(PairingAddressTry.reason($0.failure, url: $0.url))" }
                return "Could not reach \(first). Tried " + tried.joined(separator: " · ") + "."
            }
            let missed = attempts.prefix { $0.url != chosen }.map {
                "The \(PairingAddressTry.label($0.url)) address did not answer: \(PairingAddressTry.reason($0.failure, url: $0.url))."
            }
            return (["Connected through \(PairingAddressTry.label(chosen))."] + missed).joined(separator: " ")
        }
    }

    private enum Race {
        case answered(PairingFailure?)
        case timedOut
    }

    static let realSleep: @Sendable (Double) async -> Void = { seconds in
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
    }

    /// `attempt` returns nil when the address answered, else why not. `sleep` is the clock: a test injects its own, so no test waits.
    static func run(
        addresses: [String],
        budget: Double = budgetSeconds,
        sleep: @escaping @Sendable (Double) async -> Void = PairingAddressTry.realSleep,
        attempt: @escaping @Sendable (String) async -> PairingFailure?
    ) async -> Outcome {
        var attempts: [Attempt] = []
        for url in addresses.prefix(maxAddresses) {
            let result = await withTaskGroup(of: Race.self) { group -> Race in
                group.addTask { .answered(await attempt(url)) }
                group.addTask {
                    await sleep(budget)
                    return .timedOut
                }
                let first = await group.next() ?? .timedOut
                group.cancelAll()
                return first
            }
            switch result {
            case .answered(let failure): attempts.append(Attempt(url: url, failure: failure))
            case .timedOut: attempts.append(Attempt(url: url, failure: .noAnswer))
            }
            if attempts.last?.failure == nil { break }
        }
        return Outcome(attempts: attempts)
    }

    static func host(_ url: String) -> String { URL(string: url)?.host ?? url }

    /// The host with its port, as an alert names it (`10.10.10.1:8765`, #6383): which address and port were tried.
    static func address(_ url: String) -> String {
        guard let parsed = URL(string: url), let name = parsed.host else { return url }
        return parsed.port.map { "\(name):\($0)" } ?? name
    }

    static func label(_ url: String) -> String {
        let name = host(url)
        return name.lowercased().hasSuffix(".ts.net") ? "Tailscale (\(name))" : name
    }

    /// The short why for one address in the summary (the full sentence per step is `PairingFailure.sentence`).
    static func reason(_ failure: PairingFailure?, url: String) -> String {
        let tailnet = host(url).lowercased().hasSuffix(".ts.net")
        switch failure {
        case .nameNotFound?, .tailnetNameNotFound?: return "this device cannot find that name on this network"
        case .noAnswer?:
            return tailnet ? "no answer in 5 s: is Tailscale on this device?" : "no answer in 5 s: the network may keep devices apart"
        case .refused?: return "Fichero isn't listening there: turn Sharing off and on on the host"
        case .offline?: return "this device isn't connected to a network"
        case .certificatePin?, .certificateName?: return "it showed a different security key than the link"
        case .tailnetByNumber?: return "Tailscale addresses work by name, not by number"
        case .unexpected?: return "something went wrong that Fichero does not know (see Copy Details)"
        case nil: return "answered"
        default: return "it could not be reached"
        }
    }
}
