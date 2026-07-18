import Foundation
import Observation

// MARK: - ReloadDebouncer

/// Coalesces a burst of change events into a single trailing async action — the
/// #1973 beachball fix, extracted so every `ObservableDomainStore` shares ONE
/// implementation instead of re-copying the `pendingReload` task + 300ms sleep.
///
/// A store holds one of these as a stored `let` (protocol extensions can't add
/// stored properties, so the one piece of genuinely-shared *state* lives here)
/// and calls `schedule { … }` on every event whose granular patch isn't cheap
/// to reconstruct from ids alone. A workflow-run event storm then fires the
/// expensive trailing work exactly once, never once-per-event.
@MainActor
final class ReloadDebouncer {
    private var pending: Task<Void, Never>?
    private let delay: Duration

    /// `delay` defaults to the 300ms window the hand-written stores used (#1973,
    /// tuned up from 150ms in commit 2809d9d2 to coalesce extraction bursts).
    init(delay: Duration = .milliseconds(300)) {
        self.delay = delay
    }

    /// Cancel any in-flight trailing action and schedule a fresh one. Only the
    /// last call in a burst survives to run `action`.
    func schedule(_ action: @escaping @Sendable () async -> Void) {
        let delay = self.delay
        pending?.cancel()
        pending = Task {
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            await action()
        }
    }

    /// Drop any pending trailing action (teardown / explicit stop).
    func cancel() {
        pending?.cancel()
        pending = nil
    }
}

// MARK: - ObservableDomainStore

/// Generic substrate for change-stream-backed observable domain stores (#1995).
///
/// The 8 hand-written stores (EntityStore, ClaimStore, NoteStore,
/// AnnotationStore, ActionStore, ResearchStore, SearchStore, WorkflowStore) are
/// near-identical copies of the same change-stream plumbing. This protocol
/// captures the SHARED boilerplate so they — and every future domain
/// (artifact/citation/reference/…) — can drop their copies and adopt one base.
/// It is the keystone of #1935.
///
/// **Shared here (free, via the extension below):**
///   • `changeDomains` — derived from the single `changeDomain` string.
///   • `scheduleReload()` — the 300ms-debounced trailing reload (#1973), via
///     the store's `reloadDebouncer`.
///   • `resync()` — reconnect recovery; defaults to a full `reload()`.
///
/// **Supplied by each concrete store (domain-specific, NOT in the base):**
///   • `changeDomain` — e.g. `"document"`, `"entity"`.
///   • `reloadDebouncer` — a stored `let ReloadDebouncer()`.
///   • `reload()` — the scope re-fetch (a different query per store).
///   • `apply(_:)` — the granular, O(1)/non-blocking in-place update. The base
///     deliberately provides NO default: granular patching needs the concrete
///     typed collection (`entities` / `claims` / `currentDocuments`), and
///     baking a wholesale reload here would violate the beachball rule.
///
/// **Migration candidates** (do NOT migrate as part of #1995/#1996 — separate
/// de-risked follow-up): EntityStore, ClaimStore, NoteStore, AnnotationStore,
/// ActionStore, ResearchStore, SearchStore, WorkflowStore. They already work;
/// `DocumentStore` is the first/proving consumer of this base.
///
/// Adopting it composes onto the existing `@Observable final class … :
/// ChangeEventConsumer` declaration — no superclass change, no `@Observable`
/// re-application. (See docs/contributor/architecture/fichero/observable_data_layer.md.)
@MainActor
// `Sendable`: every adopter is a `@MainActor @Observable final class` (implicitly
// Sendable), so the `[weak self]` capture in `scheduleReload`'s `@Sendable`
// debounce closure is sound — but the generic `Self` needs this bound to prove it.
protocol ObservableDomainStore: ChangeEventConsumer, AnyObject, Sendable {
    /// The single event domain this store handles, e.g. `"document"`. The base
    /// turns it into the `changeDomains` set the change-stream filters on.
    /// `nonisolated` because `ChangeEventConsumer.changeDomains` is read off the
    /// main actor by the stream's `route(_:)`.
    nonisolated var changeDomain: String { get }

    /// Holds the pending trailing reload. Declare as `let reloadDebouncer =
    /// ReloadDebouncer()` (or with a custom delay) on the concrete store.
    var reloadDebouncer: ReloadDebouncer { get }

    /// Re-fetch the store's current scope. Domain-specific: a document-scoped
    /// query, an entity-scoped query, the whole library tree, etc.
    func reload() async
}

extension ObservableDomainStore {
    /// The change-stream delivers only events whose `domain` is in this set.
    nonisolated var changeDomains: Set<String> { [changeDomain] }

    /// Coalesce an expensive trailing reload onto the shared debouncer so an
    /// event storm fires the refetch once, not once-per-event (#1973). Concrete
    /// `apply(_:)` calls this for verbs whose granular patch isn't cheap to
    /// reconstruct from ids alone; cheap in-place updates (deletes) stay
    /// synchronous in `apply`.
    func scheduleReload() {
        reloadDebouncer.schedule { [weak self] in
            await self?.reload()
        }
    }

    /// Reconnect recovery (spec §5.5): after the SSE drops and reconnects we may
    /// have missed events, so re-fetch the current scope. Override only if a
    /// store wants something cheaper than a full reload.
    func resync() async {
        await reload()
    }
}
