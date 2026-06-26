@testable import Fichero
import Testing
import UniformTypeIdentifiers

struct SidebarDropProviderClassificationTests {

    @Test("text-only providers route through internal sidebar moves")
    func textOnlyProvidersRouteInternal() {
        let route = classifySidebarDropProviders([
            SidebarDropProviderCapabilities(
                canLoadURL: false,
                canLoadString: true,
                registeredTypeIdentifiers: [UTType.text.identifier]
            )
        ])

        #expect(route == .internalTextOnly)
    }

    @Test("Finder-style content provider routes external even without direct URL loading")
    func contentProviderRoutesExternal() {
        let route = classifySidebarDropProviders([
            SidebarDropProviderCapabilities(
                canLoadURL: false,
                canLoadString: false,
                registeredTypeIdentifiers: [UTType.jpeg.identifier]
            )
        ])

        #expect(route == .externalFiles)
    }

    @Test("mixed internal and Finder providers deterministically route external")
    func mixedProvidersRouteExternal() {
        let route = classifySidebarDropProviders([
            SidebarDropProviderCapabilities(
                canLoadURL: false,
                canLoadString: true,
                registeredTypeIdentifiers: [UTType.plainText.identifier]
            ),
            SidebarDropProviderCapabilities(
                canLoadURL: false,
                canLoadString: false,
                registeredTypeIdentifiers: [UTType.fileURL.identifier]
            )
        ])

        #expect(route == .externalFiles)
    }

    @Test("empty provider list is unsupported")
    func emptyProvidersUnsupported() {
        #expect(classifySidebarDropProviders([]) == .unsupported)
    }
}
