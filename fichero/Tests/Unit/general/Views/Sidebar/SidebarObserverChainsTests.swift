@testable import Fichero
import Observation
import Testing

/// The sidebar's store observers are self-re-arming `withObservationTracking` chains, which
/// have no cancel handle. `SidebarView.setupServiceObservers()` runs once per open-library-count
/// change, so without a way to supersede the previous set, one store mutation rebuilt a
/// library's sidebar tree once per call ever made (slowdown review, 2026-09-20). These drive the
/// real `SidebarObserverChains` against a real `@Observable` model — no view, no source scan.
@MainActor
struct SidebarObserverChainsTests {
    @Observable
    final class Store {
        var rows: [String] = []
        /// Observed, but not part of the signature — the status-poll churn a rebuild must skip.
        var noise = 0
    }

    /// Callback tally, by store index. A reference box: the callbacks are `@MainActor`
    /// closures, which are `Sendable` and so cannot mutate a captured `var`.
    final class Tally {
        var counts: [Int]
        init(_ stores: Int) { counts = Array(repeating: 0, count: stores) }
    }

    /// A chain answers on a later main-actor turn; give those turns room to run.
    private func settle() async {
        for _ in 0..<50 { await Task.yield() }
    }

    /// What `setupServiceObservers()` does: supersede, then arm one chain per store.
    private func setUp(_ chains: SidebarObserverChains, stores: [Store], tally: Tally) {
        chains.reset()
        for (index, store) in stores.enumerated() {
            chains.observe(
                signature: {
                    _ = store.noise
                    return store.rows.hashValue
                },
                onChange: { tally.counts[index] += 1 }
            )
        }
    }

    @Test("armed twice, mutated once: exactly one callback")
    func armedTwiceCallsBackOnce() async {
        let chains = SidebarObserverChains()
        let store = Store()
        let tally = Tally(1)
        setUp(chains, stores: [store], tally: tally)
        setUp(chains, stores: [store], tally: tally)

        store.rows.append("a")
        await settle()

        #expect(tally.counts[0] == 1, "a superseded chain must not call back alongside the live one")
    }

    @Test("set up once per arriving library: still one rebuild per change, per library")
    func oneCallbackPerChangeAcrossLibraries() async {
        let chains = SidebarObserverChains()
        let stores = [Store(), Store(), Store(), Store()]
        let tally = Tally(4)
        // Four libraries opening in turn: the observers are set up again at each new count.
        for opened in 1...stores.count {
            setUp(chains, stores: Array(stores.prefix(opened)), tally: tally)
        }

        stores[0].rows.append("a")
        await settle()
        #expect(tally.counts == [1, 0, 0, 0], "the first library was armed four times and must rebuild once")

        stores[3].rows.append("b")
        await settle()
        #expect(tally.counts == [1, 0, 0, 1], "a change in one library must not rebuild another")
    }

    @Test("a live chain keeps observing after it fires")
    func liveChainRearms() async {
        let chains = SidebarObserverChains()
        let store = Store()
        let tally = Tally(1)
        setUp(chains, stores: [store], tally: tally)

        store.rows.append("a")
        await settle()
        store.rows.append("b")
        await settle()

        #expect(tally.counts[0] == 2, "withObservationTracking is one-shot, so the chain must re-arm itself")
    }

    @Test("an observed change that leaves the signature alone does not call back, and the chain survives it")
    func unchangedSignatureIsSkipped() async {
        let chains = SidebarObserverChains()
        let store = Store()
        let tally = Tally(1)
        setUp(chains, stores: [store], tally: tally)

        store.noise += 1
        await settle()
        #expect(tally.counts[0] == 0, "a change outside the signature must not rebuild the tree")

        store.rows.append("a")
        await settle()
        #expect(tally.counts[0] == 1, "the chain must still be armed after a skipped change")
    }
}
