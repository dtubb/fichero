import Foundation
import Observation

/// Provider/model overrides for the Run Workflow submenus (#722, deduped
/// #4121). One app-wide list shared by every context menu — the sidebar row
/// and the library grid both `ensureLoaded` on menu mount and OBSERVE
/// `providers`, so N rows never fan out N fetches.
///
/// The list is cached until a Settings mutation invalidates it (#4189):
/// `ProviderAPIService` calls `invalidate()` after any successful
/// provider/model/key change, so the NEXT menu mount refetches once. The
/// engine has no `provider` change-stream domain, and every mutation path in
/// the app goes through that one service, so service-side invalidation is the
/// change signal here — not polling, not a per-open refetch.
@MainActor
@Observable
final class WorkflowRunProviderCache {
    static let shared = WorkflowRunProviderCache()

    private(set) var providers: [LLMProvider] = []
    private var loaded = false

    /// Total fetches performed — regression guard: menu re-opens with a warm
    /// cache must NOT refetch (tests assert this stays flat).
    private(set) var loadCount = 0

    /// Internal (not `private`) so tests can exercise the guard/invalidate
    /// cycle on a fresh instance; the app always uses `shared`.
    init() {}

    func ensureLoaded(chatService: ChatService?) async {
        guard let chatService else { return }
        await ensureLoaded { try await chatService.listProviders() }
    }

    /// Same load-once guard with an injectable fetch (test seam).
    func ensureLoaded(fetch: () async throws -> [LLMProvider]) async {
        guard !loaded else { return }
        do {
            providers = try await fetch()
            loaded = true
            loadCount += 1
        } catch {
            // Non-fatal; keep menu usable with Default option.
        }
    }

    /// The provider or model set changed (Settings → AI): drop the load-once
    /// guard so the next menu mount refetches. The stale list stays visible
    /// until then — an open menu must not blank out mid-interaction.
    func invalidate() {
        loaded = false
    }
}
