@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@Suite("APIClient generated-client wrapper")
struct APIClientTests {
    @Test("APIClient wraps a FicheroClient configured at the engine host")
    @MainActor
    func wrapsFicheroClientAtEngineHost() {
        let customHost = URL(string: "https://tailnet.example:8765")!
        let client = APIClient(baseURL: customHost, libraryPath: "/tmp/Test.fichero")

        #expect(client.client.baseURL == customHost)
        #expect(client.baseURL == customHost.appendingPathComponent("api"))
        #expect(client.currentLibraryPath == "/tmp/Test.fichero")
    }

    @Test("Library path propagates to the wrapped FicheroClient")
    @MainActor
    func propagatesLibraryPath() {
        let client = APIClient()

        client.currentLibraryPath = "/Users/example/Library.fichero"

        #expect(client.client.currentLibraryPath == "/Users/example/Library.fichero")
    }

    @Test("Exposes the generated OpenAPI client")
    @MainActor
    func exposesGeneratedClient() {
        let client = APIClient(baseURL: URL(string: "https://127.0.0.1:8765")!)

        // `api` returns the generated `Client` from FicheroAPIClient.
        #expect(client.api is Client)
    }
}
