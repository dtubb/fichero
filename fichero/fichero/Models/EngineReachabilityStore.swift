import FicheroAPIClient
import Foundation
import Observation

/// Whether the engine answers, after a write could not reach it (13b, "out of reach of the engine the
/// text is read-only"). The STORE owns the health probe -- a view never calls the client (the observable
/// data layer) -- and a surface follows `reachable` (`tellEachChange`), saying so on each change only.
@MainActor
@Observable
final class EngineReachabilityStore {
    private(set) var reachable = true
    /// Why the last write could not reach the engine; nil while it answers.
    private(set) var reason: String?

    @ObservationIgnored private var probe: Task<Void, Never>?
    @ObservationIgnored private let isBack: @MainActor () async -> Bool
    @ObservationIgnored private let pause: @MainActor () async -> Void

    init(isBack: @escaping @MainActor () async -> Bool, pause: @escaping @MainActor () async -> Void) {
        self.isBack = isBack
        self.pause = pause
    }

    /// The engine's own health (`GET /api/health`), asked every 3 s while it is out of reach.
    convenience init(client: FicheroClient) {
        self.init(
            isBack: {
                guard let response = try? await client.api.healthCheckApiHealthGet(.init()), case .ok = response else {
                    return false
                }
                return true
            },
            // ponytail: a fixed 3 s probe; back off if a long outage makes this chatty.
            pause: { try? await Task.sleep(nanoseconds: 3_000_000_000) }
        )
    }

    /// A write could not reach the engine: it is out of reach until its health answers. One probe at a
    /// time, however many writes fail meanwhile.
    func wentAway(_ reason: String) {
        self.reason = reason
        if reachable { reachable = false }
        guard probe == nil else { return }
        let isBack = isBack, pause = pause
        probe = Task { [weak self] in
            while !Task.isCancelled {
                await pause()
                if await isBack() { break }
            }
            guard let self, !Task.isCancelled else { return }
            self.reason = nil
            self.reachable = true
            self.probe = nil
        }
    }

    /// Say each CHANGE of `reachable` -- never the steady state, never twice -- as the Reader page's
    /// `engineState` script. The page starts out assuming the engine is there, so that is the baseline.
    func tellEachChange(_ tell: @MainActor (String) async -> Void) async {
        var last = true
        for await now in Observations({ self.reachable }) {
            guard now != last else { continue }
            last = now
            await tell(ReaderTextEdit.engineStateScript(reachable: now, reason: now ? nil : reason))
        }
    }
}
