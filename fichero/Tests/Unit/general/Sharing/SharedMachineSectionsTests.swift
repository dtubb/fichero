import Foundation
import Testing

@testable import Fichero

/// The Mac sidebar lists every paired Mac (`sharing.guest.machines-group`, #6459).
@MainActor
struct SharedMachineSectionsTests {
    /// A paired Mac that shared nothing yet is still listed, with its own sentence, and is not "no Macs yet".
    @Test func aPairedMacThatSharedNothingIsListedWithItsOwnSentence() {
        let machines = [PairedMachine(id: "https://a:8765", name: "a", libraries: [])]
        #expect(!SharedMachineSections.showsHowToPair(machines))
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.map(\.machine.name) == ["a"])
        #expect(sections.first?.rows == [.nothingShared("a hasn't shared any project yet")])
    }

    @Test func noPairedMacShowsHowToPair() {
        #expect(SharedMachineSections.showsHowToPair([]))
    }

    @Test func eachPairedMacKeepsItsOwnLibrariesInOrder() {
        let machines = [PairedMachine(id: "https://a:8765", name: "a", libraries: ["/x/One", "/x/Two"]),
                        PairedMachine(id: "https://b:8765", name: "b", libraries: [])]
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.first?.rows == [.library("/x/One"), .library("/x/Two")])
        #expect(sections.count == 2)
    }
}
