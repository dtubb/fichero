import Observation

/// The sidebar's self-re-arming `withObservationTracking` chains, with the one thing a bare
/// chain cannot have: a way to stop.
///
/// `withObservationTracking` is one-shot and returns no handle, so a chain that re-arms itself
/// lives for ever. `SidebarView.setupServiceObservers()` runs from the view's `.task` AND on every
/// open-library-count change, and each run used to ADD a full set of chains on top of the ones
/// already armed — with four libraries opening in turn the first library ended up with four, so
/// one store mutation rebuilt its sidebar tree four times back to back (slowdown review,
/// 2026-09-20). `reset()` bumps a generation token; a chain armed under an older generation
/// neither calls back nor re-arms when it next fires.
///
/// A reference type because the token must be shared by every chain and outlive any one copy of
/// the `View` struct that armed them.
@MainActor
final class SidebarObserverChains {
    private var generation = 0
    private var nextChainId = 0
    /// The signature each live chain saw the last time it armed, by chain id.
    private var lastSignatures: [Int: Int] = [:]

    /// Supersede every chain armed so far. They stop at their next fire.
    func reset() {
        generation += 1
        lastSignatures.removeAll()
    }

    /// Arm one chain. `signature` reads the observed properties (that read IS the tracking
    /// registration) and folds them to the value that decides whether a change matters:
    /// `onChange` runs only when the signature differs from the one this chain saw at its
    /// previous arm — the "skip a no-op rebuild" rule the document-store observer already had
    /// (#3862), now shared by every observer.
    func observe(
        signature: @escaping @MainActor () -> Int,
        onChange: @escaping @MainActor () -> Void
    ) {
        nextChainId += 1
        arm(chain: nextChainId, generation: generation, signature: signature, onChange: onChange)
    }

    private func arm(
        chain: Int,
        generation armed: Int,
        signature: @escaping @MainActor () -> Int,
        onChange: @escaping @MainActor () -> Void
    ) {
        let now = withObservationTracking {
            signature()
        } onChange: { [weak self] in
            Task { @MainActor in
                guard let self, self.generation == armed else { return }
                self.arm(chain: chain, generation: armed, signature: signature, onChange: onChange)
            }
        }
        let previous = lastSignatures.updateValue(now, forKey: chain)
        if let previous, previous != now {
            onChange()
        }
    }
}
