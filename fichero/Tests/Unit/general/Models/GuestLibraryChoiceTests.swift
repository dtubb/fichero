//
//  GuestLibraryChoiceTests.swift
//  FicheroTests
//
//  `sharing.guest-addresses-the-hosts-library` (#5965): a paired guest addresses a library the host serves, never its own path.
//

@testable import Fichero
import Testing

@Suite("Guest library choice")
struct GuestLibraryChoiceTests {
    private let phone = "/var/mobile/Containers/Data/Application/ABC/Documents/global.fichero"

    @Test("a pairing that carried the host's library path keeps it")
    func pairedPathWins() {
        #expect(GuestLibraryChoice.choose(paired: "/Users/ana/Documents/Diaries.fichero", accessible: ["/Users/ana/other.fichero"])
            == .path("/Users/ana/Documents/Diaries.fichero"))
    }

    @Test("with no paired path the host's only library is adopted, never the guest's own")
    func onlyLibrary() {
        let chosen = GuestLibraryChoice.choose(paired: " ", accessible: ["/Users/ana/Documents/Diaries.fichero"])
        #expect(chosen == .path("/Users/ana/Documents/Diaries.fichero"))
        #expect(chosen != .path(phone))
    }

    @Test("with several, the host's global one; else the most recently used (first)")
    func severalLibraries() {
        #expect(GuestLibraryChoice.choose(paired: "", accessible: ["/Users/ana/A.fichero", "/Users/ana/Library/global.fichero"])
            == .path("/Users/ana/Library/global.fichero"))
        #expect(GuestLibraryChoice.choose(paired: "", accessible: ["/Users/ana/A.fichero", "/Users/ana/B.fichero"])
            == .path("/Users/ana/A.fichero"))
    }

    @Test("when the host serves nothing the guest says so and addresses nothing")
    func nothingServed() {
        #expect(GuestLibraryChoice.choose(paired: "", accessible: []) == .none)
        #expect(GuestLibraryChoice.noneServedWords.hasPrefix("The Mac you are connected to"))
    }
}
