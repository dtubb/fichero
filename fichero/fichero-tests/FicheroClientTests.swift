import Foundation
@testable import FicheroAPIClient
import Testing

@Suite("FicheroClient host rebinding")
struct FicheroClientTests {
    @Test("reconfigure updates the generated client host")
    @MainActor
    func reconfigureUpdatesBaseURL() {
        let originalURL = URL(string: "http://127.0.0.1:8765")!
        let remoteURL = URL(string: "https://host.tailnet.example")!
        let client = FicheroClient(baseURL: originalURL, libraryPath: "/tmp/Test.fichero")

        #expect(client.baseURL == originalURL)
        #expect(client.currentLibraryPath == "/tmp/Test.fichero")

        client.reconfigure(baseURL: remoteURL)

        #expect(client.baseURL == remoteURL)
        #expect(client.currentLibraryPath == "/tmp/Test.fichero")
    }
}
