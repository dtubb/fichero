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
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Services/ProviderAPIService.swift")
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
}
