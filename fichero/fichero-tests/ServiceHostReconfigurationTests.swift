@testable import Fichero
import Foundation
import Testing

@Suite("App-wide host rebinding")
struct ServiceHostReconfigurationTests {
    private func restoreEngineHost(_ value: String?) {
        if let value {
            UserDefaults.standard.set(value, forKey: EngineConfig.userDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: EngineConfig.userDefaultsKey)
        }
    }

    @MainActor
    private func waitForHostUpdate(
        _ expectedHost: URL,
        service: IntegrationsService
    ) async {
        for _ in 0..<20 {
            if service.client.baseURL == expectedHost {
                return
            }
            try? await Task.sleep(for: .milliseconds(10))
        }
    }

    @MainActor
    private func waitForHostUpdate(
        _ expectedHost: URL,
        service: ModelComparisonService
    ) async {
        for _ in 0..<20 {
            if service.client.baseURL == expectedHost {
                return
            }
            try? await Task.sleep(for: .milliseconds(10))
        }
    }

    @Test("IntegrationsService rebinds when the engine host changes")
    @MainActor
    func integrationsServiceRebindsOnHostChangeNotification() async {
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }

        let firstHost = URL(string: "https://first.tailnet.example")!
        let secondHost = URL(string: "https://second.tailnet.example")!
        UserDefaults.standard.set(firstHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

        let service = IntegrationsService()
        #expect(service.client.baseURL == firstHost)

        UserDefaults.standard.set(secondHost.absoluteString, forKey: EngineConfig.userDefaultsKey)
        NotificationCenter.default.post(name: EngineConfig.engineHostDidChangeNotification, object: nil)
        await waitForHostUpdate(secondHost, service: service)

        #expect(service.client.baseURL == secondHost)
    }

    @Test("ModelComparisonService rebinds when the engine host changes")
    @MainActor
    func modelComparisonServiceRebindsOnHostChangeNotification() async {
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }

        let firstHost = URL(string: "https://first.tailnet.example")!
        let secondHost = URL(string: "https://second.tailnet.example")!
        UserDefaults.standard.set(firstHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

        let service = ModelComparisonService()
        #expect(service.client.baseURL == firstHost)

        UserDefaults.standard.set(secondHost.absoluteString, forKey: EngineConfig.userDefaultsKey)
        NotificationCenter.default.post(name: EngineConfig.engineHostDidChangeNotification, object: nil)
        await waitForHostUpdate(secondHost, service: service)

        #expect(service.client.baseURL == secondHost)
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

        apiClient.reconfigure(baseURL: second)

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
        apiClient.reconfigure(baseURL: URL(string: "https://second.tailnet.example")!)
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

        apiClient.reconfigure(baseURL: second)

        // Same service instance now resolves the preview against the new host —
        // no reconstruction, no stranded localhost.
        #expect(service.previewURL(documentId: "doc1", applyEdits: false).host == "second.tailnet.example")
    }
}
