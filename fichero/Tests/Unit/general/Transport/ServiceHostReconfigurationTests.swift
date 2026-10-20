@testable import Fichero
import Foundation
import Testing

/// #5703: these tests write the engine host and post the app-wide host-change notification. They ran in parallel
/// with each other (and with anything else under Swift Testing) against ONE shared preference suite, so one test's
/// write or restore changed the host under the other's service mid-rebind, and its wait for its own host timed out.
/// Now each host-writing test reads and writes a suite of its own (`EngineConfig.withIsolatedTestDefaults`): the
/// service's init and the rebind the notification starts both run in that test's scope, so they see only its host.
/// `.serialized` too, as these tests share the one notification name, and each uses hosts no other test does.
@Suite("App-wide host rebinding", .serialized)
struct ServiceHostReconfigurationTests {
    @MainActor
    private func waitForHostUpdate(_ expectedHost: URL, of client: () -> URL) async {
        for _ in 0..<200 {
            if client() == expectedHost { return }
            try? await Task.sleep(for: .milliseconds(10))
        }
    }

    @Test("IntegrationsService rebinds when the engine host changes")
    @MainActor
    func integrationsServiceRebindsOnHostChangeNotification() async {
        await EngineConfig.withIsolatedTestDefaults {
            let firstHost = URL(string: "https://integrations-first.tailnet.example")!
            let secondHost = URL(string: "https://integrations-second.tailnet.example")!
            EngineConfig.defaults.set(firstHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

            let service = IntegrationsService()
            #expect(service.client.baseURL == firstHost)

            EngineConfig.defaults.set(secondHost.absoluteString, forKey: EngineConfig.userDefaultsKey)
            NotificationCenter.default.post(name: EngineConfig.engineHostDidChangeNotification, object: nil)
            await waitForHostUpdate(secondHost) { service.client.baseURL }

            #expect(service.client.baseURL == secondHost)
            // The rebind re-reads HOW to dial too, not just the URL (a host-only rebind left Activity on a stale endpoint after Sharing).
            #expect(service.client.transportMode == EngineConfig.transportMode)
        }
    }

    @Test("ModelComparisonService rebinds when the engine host changes")
    @MainActor
    func modelComparisonServiceRebindsOnHostChangeNotification() async {
        await EngineConfig.withIsolatedTestDefaults {
            let firstHost = URL(string: "https://comparison-first.tailnet.example")!
            let secondHost = URL(string: "https://comparison-second.tailnet.example")!
            EngineConfig.defaults.set(firstHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

            let service = ModelComparisonService()
            #expect(service.client.baseURL == firstHost)

            EngineConfig.defaults.set(secondHost.absoluteString, forKey: EngineConfig.userDefaultsKey)
            NotificationCenter.default.post(name: EngineConfig.engineHostDidChangeNotification, object: nil)
            await waitForHostUpdate(secondHost) { service.client.baseURL }

            #expect(service.client.baseURL == secondHost)
            // The rebind re-reads HOW to dial too, not just the URL (a host-only rebind left Activity on a stale endpoint after Sharing).
            #expect(service.client.transportMode == EngineConfig.transportMode)
        }
    }

    /// The seam itself: a test's own suite is what `EngineConfig` reads, and the shared suite never sees its writes.
    @Test("a test's own preference suite stands in for the shared one, and is gone afterwards")
    @MainActor
    func isolatedDefaultsStandIn() async {
        let shared = EngineConfig.defaults
        let before = shared.string(forKey: EngineConfig.userDefaultsKey)
        let host = URL(string: "https://isolated.tailnet.example")!
        await EngineConfig.withIsolatedTestDefaults {
            #expect(EngineConfig.defaults !== shared)
            #expect(EngineConfig.defaults.string(forKey: EngineConfig.userDefaultsKey) == nil, "it starts empty")
            EngineConfig.defaults.set(host.absoluteString, forKey: EngineConfig.userDefaultsKey)
            #expect(EngineConfig.host == host)
        }
        #expect(EngineConfig.defaults === shared)
        #expect(shared.string(forKey: EngineConfig.userDefaultsKey) == before, "the shared suite is untouched")
    }

    // #2349: the legacy `APIClient` wraps its OWN `FicheroClient`, separate from
    // the shared generated `ficheroClient`. DocumentStore, ChainService, and the
    // app-wide MCPService are all built on `APIClient`, so if `reconfigure` didn't
    // rebind the wrapped client they kept talking to the old (localhost) host after
    // pairing. These pin the in-place rebind + library-path preservation.
    @Test("APIClient.reconfigure rebinds its wrapped FicheroClient")
    @MainActor
    func apiClientReconfigureRebindsWrappedClient() {
        let first = URL(string: "https://first.tailnet.example")!
        let second = URL(string: "https://second.tailnet.example")!

        let apiClient = APIClient(baseURL: first, libraryPath: "/tmp/Lib.fichero")
        #expect(apiClient.client.baseURL == first)
        #expect(apiClient.baseURL == first.appendingPathComponent("api"))

        apiClient.reconfigure(baseURL: second, transportMode: .https)

        // The wrapped client — the SAME reference every apiClient-based service
        // holds — now points at the new host, with no reconstruction.
        #expect(apiClient.client.baseURL == second)
        #expect(apiClient.baseURL == second.appendingPathComponent("api"))
    }

    @Test("APIClient.reconfigure preserves the library path")
    @MainActor
    func apiClientReconfigurePreservesLibraryPath() {
        let apiClient = APIClient(
            baseURL: URL(string: "https://first.tailnet.example")!,
            libraryPath: "/tmp/Lib.fichero"
        )
        apiClient.reconfigure(baseURL: URL(string: "https://second.tailnet.example")!, transportMode: .https)
        // The library path must survive the host rebind — else the first request
        // to the new host would drop X-Fichero-Library-Path.
        #expect(apiClient.currentLibraryPath == "/tmp/Lib.fichero")
        #expect(apiClient.client.currentLibraryPath == "/tmp/Lib.fichero")
    }

    // #2349: ImageEditingService's raw-bytes `previewURL` path bypasses
    // the generated `client.api` and builds URLs off the engine root directly.
    // It must read that root LIVE off the shared wrapped client (not a snapshot),
    // or image previews stay pinned to the host that was current when the editor
    // opened after a mid-session pairing / Settings host change.
    @Test("ImageEditingService previewURL follows an apiClient host rebind")
    @MainActor
    func imageEditingPreviewURLFollowsRebind() {
        let first = URL(string: "https://first.tailnet.example")!
        let second = URL(string: "https://second.tailnet.example")!

        let apiClient = APIClient(baseURL: first, libraryPath: "/tmp/Lib.fichero")
        let service = ImageEditingService(apiClient: apiClient)
        #expect(service.previewURL(documentId: "doc1", applyEdits: false).host == "first.tailnet.example")

        apiClient.reconfigure(baseURL: second, transportMode: .https)

        // Same service instance now resolves the preview against the new host —
        // no reconstruction, no stranded localhost.
        #expect(service.previewURL(documentId: "doc1", applyEdits: false).host == "second.tailnet.example")
    }
}
