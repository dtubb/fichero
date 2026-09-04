@testable import Fichero
import Foundation
import XCTest

/// #4189 — adding a model in Settings must reach the Run Workflow context
/// submenus. The cache is load-once for menu-open economy (N rows share one
/// fetch), so a Settings mutation has to drop the guard: ProviderAPIService
/// invalidates on every successful provider/model/key change and the NEXT
/// menu mount refetches. Without invalidation the submenu showed the model
/// set from first launch forever.
@MainActor
final class WorkflowRunProviderCacheTests: XCTestCase {
    private static func provider(_ id: String, models: [String]) -> LLMProvider {
        LLMProvider(id: id, name: id, models: models, available: true, supportsVision: false)
    }

    func testEnsureLoadedFetchesOnceAcrossRepeatedMenuMounts() async {
        let cache = WorkflowRunProviderCache()
        var fetches = 0

        for _ in 0..<3 {
            await cache.ensureLoaded {
                fetches += 1
                return [Self.provider("ollama", models: ["llama3"])]
            }
        }

        // Menu re-opens with a warm cache must not refetch (the whole reason
        // the guard exists — every visible sidebar row mounts this).
        XCTAssertEqual(fetches, 1)
        XCTAssertEqual(cache.loadCount, 1)
        XCTAssertEqual(cache.providers.map(\.id), ["ollama"])
    }

    func testInvalidateMakesTheNextMountPickUpTheNewModelSet() async {
        let cache = WorkflowRunProviderCache()
        await cache.ensureLoaded { [Self.provider("ollama", models: ["llama3"])] }

        // Settings adds a model → ProviderAPIService invalidates.
        cache.invalidate()

        // The stale list stays visible until the next mount (an open menu
        // must not blank out) …
        XCTAssertEqual(cache.providers.first?.models, ["llama3"])

        // … and the next menu mount refetches the grown model set.
        await cache.ensureLoaded { [Self.provider("ollama", models: ["llama3", "glm-5.2"])] }
        XCTAssertEqual(cache.providers.first?.models, ["llama3", "glm-5.2"])
        XCTAssertEqual(cache.loadCount, 2)
    }

    func testFailedFetchDoesNotLatchTheGuard() async {
        struct Boom: Error {}
        let cache = WorkflowRunProviderCache()

        await cache.ensureLoaded { throw Boom() }
        XCTAssertTrue(cache.providers.isEmpty)
        XCTAssertEqual(cache.loadCount, 0)

        // A transient failure (engine still starting) must not freeze the
        // menu on "Default only" forever — the next mount retries.
        await cache.ensureLoaded { [Self.provider("openai", models: ["gpt-5.5"])] }
        XCTAssertEqual(cache.providers.map(\.id), ["openai"])
    }

    func testNilChatServiceIsANoOpAndDoesNotLatch() async {
        let cache = WorkflowRunProviderCache()

        await cache.ensureLoaded(chatService: nil)
        XCTAssertTrue(cache.providers.isEmpty)
        XCTAssertEqual(cache.loadCount, 0)

        // A library that had no chat service yet must still load later.
        await cache.ensureLoaded { [Self.provider("mlx", models: ["qwen"])] }
        XCTAssertEqual(cache.providers.map(\.id), ["mlx"])
    }

    // MARK: - Regression: every mutation path invalidates

    func testEveryProviderMutationEndpointInvalidatesTheRunMenus() throws {
        let url = try AppSource.root().appendingPathComponent("Services/ProviderAPIService.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        // One invalidation per successful mutation: create/update/delete
        // provider, set/delete API key, add/remove model, add/update/delete
        // provider ref. Read-only endpoints (list/get/status/test) must NOT
        // invalidate — that would refetch on every Settings visit.
        let calls = source.components(separatedBy: "invalidateRunWorkflowProviderMenus()").count - 1
        XCTAssertEqual(
            calls, 11,  // 1 definition + 10 mutation sites
            "provider mutations and run-menu invalidation went out of sync"
        )
        XCTAssertTrue(source.contains("WorkflowRunProviderCache.shared.invalidate()"))
    }

    // MARK: - #4276: out-of-app provider changes arrive via the change stream

    /// A provider added from ANOTHER window / device / the CLI never goes
    /// through this app's ProviderAPIService — the engine broadcasts
    /// `provider.*` on every library's change stream and WorkflowStore (an
    /// already-registered consumer) must drop the run-menu cache on it, and
    /// on resync (reconnect may have missed provider events).
    func testWorkflowStoreDropsRunMenuCacheOnProviderEvents() throws {
        let url = try AppSource.root().appendingPathComponent("Models/WorkflowStore.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        XCTAssertTrue(
            source.contains("\"provider\""),
            "WorkflowStore must subscribe to the provider change domain (#4276)"
        )
        let invalidations = source.components(
            separatedBy: "WorkflowRunProviderCache.shared.invalidate()"
        ).count - 1
        XCTAssertEqual(
            invalidations, 2,
            "WorkflowStore must invalidate the run-menu cache on provider events AND on resync (#4276)"
        )
    }
}

// MARK: - #4560: the cache must say WHICH of the three states it is in

extension WorkflowRunProviderCacheTests {
    /// A spinner is a promise that something is still coming. The model chip
    /// showed one whenever it had no rows, including after the load had
    /// finished — so a finished-and-empty list and a failed list both read as
    /// "Loading models…" forever. `loaded` is what lets the chip tell the
    /// difference; before #4560 it was private and the chip could not ask.
    func testFreshCacheHasNotLoadedSoTheChipMaySpin() {
        let cache = WorkflowRunProviderCache()

        XCTAssertFalse(cache.loaded)
        XCTAssertFalse(cache.lastLoadFailed)
    }

    func testLoadedButEmptyIsLoadedNotLoading() async {
        let cache = WorkflowRunProviderCache()

        await cache.ensureLoaded { [] }

        // The load HAPPENED and produced nothing. Nothing further is coming,
        // so the chip must stop promising that it is.
        XCTAssertTrue(cache.loaded)
        XCTAssertFalse(cache.lastLoadFailed)
        XCTAssertTrue(cache.providers.isEmpty)
    }

    func testAFailedLoadIsReportedAsFailedNotAsStillLoading() async {
        struct Boom: Error {}
        let cache = WorkflowRunProviderCache()

        await cache.ensureLoaded { throw Boom() }

        XCTAssertTrue(cache.lastLoadFailed)
        // Still not loaded, so the guard lets the next menu mount retry —
        // but the chip reads `lastLoadFailed` first and says the engine did
        // not answer rather than spinning on a load that already failed.
        XCTAssertFalse(cache.loaded)
    }

    func testASuccessfulLoadAfterAFailureClearsTheFailure() async {
        struct Boom: Error {}
        let cache = WorkflowRunProviderCache()

        await cache.ensureLoaded { throw Boom() }
        await cache.ensureLoaded { [Self.provider("omlx", models: ["Chandra-OCR"])] }

        XCTAssertTrue(cache.loaded)
        XCTAssertFalse(cache.lastLoadFailed)
        XCTAssertEqual(cache.providers.first?.models, ["Chandra-OCR"])
    }
}
