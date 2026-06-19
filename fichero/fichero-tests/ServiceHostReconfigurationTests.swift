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
}
