#if os(macOS)
import Foundation
import Testing

@testable import Fichero

@Suite("UI test support")
struct UITestSupportTests {
    @Test("library override comes from launch argument first")
    func libraryOverrideFromLaunchArgument() {
        let url = uiTestLibraryOverrideURL(
            arguments: ["Fichero", "--uitesting", "--fichero-library", "/tmp/Seed.fichero"],
            environment: ["FICHERO_UITEST_LIBRARY": "/tmp/Env.fichero"]
        )

        #expect(url?.path == "/tmp/Seed.fichero")
    }

    @Test("library override falls back to environment")
    func libraryOverrideFromEnvironment() {
        let url = uiTestLibraryOverrideURL(
            arguments: ["Fichero", "--uitesting"],
            environment: ["FICHERO_UITEST_LIBRARY": "/tmp/Env.fichero"]
        )

        #expect(url?.path == "/tmp/Env.fichero")
    }

    @Test("library override is disabled outside UI testing")
    func libraryOverrideRequiresUITestingFlag() {
        let url = uiTestLibraryOverrideURL(
            arguments: ["Fichero", "--fichero-library", "/tmp/Seed.fichero"],
            environment: ["FICHERO_UITEST_LIBRARY": "/tmp/Env.fichero"]
        )

        #expect(url == nil)
    }
}
#endif
