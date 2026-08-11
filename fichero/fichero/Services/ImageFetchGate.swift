import Foundation

/// Bounds concurrent image fetches (2026-08-10): a scroll burst fired one
/// thumbnail request per visible tile with NO bound — 48 of the transport's
/// 64 connections in flight at once (the ConnectionPool tripwire), and a
/// folder import died with getConnectionFromPoolTimeout because the
/// ingest-status poll could not get a connection. Images are the app's only
/// unbounded fan-out; gating THEM keeps pool headroom for everything else.
/// 12 saturates a local engine without starving the pool.
@MainActor
final class ImageFetchGate {
    private let slots: Int
    private var inFlight = 0
    private var waiters: [CheckedContinuation<Void, Never>] = []

    init(slots: Int) {
        self.slots = slots
    }

    func acquire() async {
        if inFlight < slots {
            inFlight += 1
            return
        }
        await withCheckedContinuation { waiters.append($0) }
        // The releaser hands the slot over without decrementing, so the
        // count stays correct across the handoff.
        inFlight += 1
    }

    func release() {
        inFlight -= 1
        if !waiters.isEmpty {
            waiters.removeFirst().resume()
        }
    }
}
