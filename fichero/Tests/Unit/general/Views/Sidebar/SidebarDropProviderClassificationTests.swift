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
        // A Finder file drag (e.g. a PDF) advertises public.file-url. It DOES
        // conform to public.item, but live drags showed no targeting with
        // `.item` alone — rows accept `.fileURL` explicitly, like the library
        // header does. Keep both explicit entries locked.
        #expect(SidebarItemRow.dropTypes.contains(.fileURL))
        #expect(SidebarItemRow.dropTypes.contains(.utf8PlainText))
    }

    @Test("#3390 payload: a Finder PDF drag classifies as external files")
    func pdfFinderDragRoutesExternal() {
        // The exact provider shape a Finder PDF drag presents: loadable URL,
        // no string, file-url + pdf UTIs registered. Must route to the
        // external-file import path, never the internal text-move path.
        let route = classifySidebarDropProviders([
            SidebarDropProviderCapabilities(
                canLoadURL: true,
                canLoadString: false,
                registeredTypeIdentifiers: [UTType.fileURL.identifier, UTType.pdf.identifier]
            )
        ])

        #expect(route == .externalFiles)
    }
}

// MARK: - #4124 regression: the REAL internal-drag shape

extension SidebarDropProviderClassificationTests {

    @Test("internal .draggable string drag (utf8-plain-text only) routes to the move path")
    func internalUTF8DragIsInternal() {
        // The actual shape `.draggable(SidebarDragID)` produces registers
        // ONLY public.utf8-plain-text — the classifier's exclusion list
        // missed it, so every row-onto-row sidebar move was misrouted to
        // the external-file importer and silently died (#4124).
        let route = classifySidebarDropProviders([
            SidebarDropProviderCapabilities(
                canLoadURL: false,
                canLoadString: true,
                registeredTypeIdentifiers: [UTType.utf8PlainText.identifier]
            )
        ])
        #expect(route == .internalTextOnly)
    }

    @Test("every plain-text UTI variant stays internal")
    func plainTextVariantsAreInternal() {
        for uti in [UTType.text.identifier, UTType.plainText.identifier, UTType.utf8PlainText.identifier] {
            let route = classifySidebarDropProviders([
                SidebarDropProviderCapabilities(
                    canLoadURL: false,
                    canLoadString: true,
                    registeredTypeIdentifiers: [uti]
                )
            ])
            #expect(route == .internalTextOnly, "\(uti)")
        }
    }

    @Test("text-typed provider that can't load a string is unsupported, not external")
    func unloadableTextProviderIsUnsupported() {
        let route = classifySidebarDropProviders([
            SidebarDropProviderCapabilities(
                canLoadURL: false,
                canLoadString: false,
                registeredTypeIdentifiers: [UTType.plainText.identifier]
            )
        ])
        #expect(route == .unsupported)
    }
}
