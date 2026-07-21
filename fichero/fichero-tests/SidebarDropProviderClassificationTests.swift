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

    @Test("#3390 sidebar rows accept file-url drops (not just .item)")
    func rowsAcceptFileURLDrops() {
        // A Finder file drag (e.g. a PDF) advertises public.file-url, which does
        // NOT conform to public.item — so accepting `.item` alone left file drops
        // dead. The row must accept `.fileURL` like the library header does.
        #expect(SidebarItemRow.dropTypes.contains(.fileURL))
        #expect(SidebarItemRow.dropTypes.contains(.utf8PlainText))
    }
}
