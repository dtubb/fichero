@testable import Fichero
import Testing

/// A guest-only device (an iPad paired to a Mac) draws the always-there section only while it holds the host's paired
/// library; a Mac always draws its own (`sidebar.guest-has-no-library-of-its-own`).
struct AlwaysThereOnAGuestTests {
    @Test func aMacAlwaysDrawsItsOwn() {
        #expect(SidebarProjectSections.showsAlwaysThere(
            requiresExternalEngine: false, alwaysTherePath: "/Library/Application Support/Fichero/global.fichero",
            pairedLibraryPath: ""
        ))
    }

    @Test func aGuestDrawsTheHostsAdoptedLibrary() {
        #expect(SidebarProjectSections.showsAlwaysThere(
            requiresExternalEngine: true, alwaysTherePath: "/Volumes/Archive/Project.fichero",
            pairedLibraryPath: "/Volumes/Archive/Project.fichero/"
        ))
    }

    @Test func aGuestHidesItsOwnGlobalPackage() {
        #expect(!SidebarProjectSections.showsAlwaysThere(
            requiresExternalEngine: true, alwaysTherePath: "/var/mobile/Library/Application Support/Fichero/global.fichero",
            pairedLibraryPath: "/Volumes/Archive/Project.fichero"
        ))
    }

    @Test func aGuestNotYetPairedDrawsNothing() {
        #expect(!SidebarProjectSections.showsAlwaysThere(
            requiresExternalEngine: true, alwaysTherePath: "/var/mobile/Library/Application Support/Fichero/global.fichero",
            pairedLibraryPath: ""
        ))
    }
}
