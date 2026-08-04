@testable import Fichero
import FicheroAPIClient
import XCTest

/// #3222 — the AI-settings store must SURFACE every persistence failure, never
/// swallow it (the silent `try?` that showed seeded values as if saved). These
/// exercise the store's error-surfacing paths through a fake endpoint that throws.
@MainActor
final class AISettingsStoreTests: XCTestCase {

    private struct StubError: LocalizedError {
        var errorDescription: String? { "stub failure" }
    }

    /// Fake endpoint seam (AIDefaultsProviding) so the store's error handling is
    /// tested without a live backend. No apple provider, so `load()` never seeds —
    /// each test drives exactly one failing call.
    private final class FakeEndpoint: AIDefaultsProviding {
        var providers: [Components.Schemas.ProviderResponse] = []
        var fetchError: Error?
        var saveError: Error?
        var resetError: Error?

        func loadProviders() async {}
        func fetchAIDefaults() async throws -> AIDefaults {
            if let fetchError { throw fetchError }
            return AIDefaults()
        }
        func saveAIDefaults(_ defaults: AIDefaults) async throws {
            if let saveError { throw saveError }
        }
        func resetAIDefaults() async throws {
            if let resetError { throw resetError }
        }
    }

    func testLoadSurfacesFetchFailureInsteadOfSwallowing() async {
        let fake = FakeEndpoint()
        fake.fetchError = StubError()
        let store = AISettingsStore()
        store.attach(fake)

        await store.load()

        XCTAssertEqual(store.errorMessage, "Failed to load: stub failure")
        XCTAssertFalse(store.isLoading, "isLoading must clear even on failure")
    }

    func testSaveSurfacesFailure() async {
        let fake = FakeEndpoint()
        let store = AISettingsStore()
        store.attach(fake)
        await store.load()               // clears isLoading; empty fetch, no seed
        fake.saveError = StubError()

        await store.save()

        XCTAssertEqual(store.errorMessage, "Failed to save: stub failure")
    }

    func testResetSurfacesFailure() async {
        let fake = FakeEndpoint()
        fake.resetError = StubError()
        let store = AISettingsStore()
        store.attach(fake)

        await store.reset()

        XCTAssertEqual(store.errorMessage, "Failed to reset: stub failure")
    }

    /// The clean path leaves no error and stops loading — so a stale error never
    /// lingers over a successful load.
    func testSuccessfulLoadLeavesNoError() async {
        let fake = FakeEndpoint()
        let store = AISettingsStore()
        store.attach(fake)

        await store.load()

        XCTAssertNil(store.errorMessage)
        XCTAssertFalse(store.isLoading)
    }

    /// With no endpoint attached the store stays inert rather than crashing — the
    /// view attaches in `.task`, so a call before that must be a safe no-op.
    func testCallsAreNoOpBeforeAttach() async {
        let store = AISettingsStore()
        await store.save()
        await store.reset()
        XCTAssertNil(store.errorMessage)
    }
}
