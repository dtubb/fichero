import Foundation
import Testing

@testable import Fichero

/// The Mac sidebar lists every paired Mac (`sharing.guest.machines-group`, #6459), and nothing until one is paired
/// (`sharing.guest.no-section-until-paired`).
@MainActor
struct SharedMachineSectionsTests {
    /// A paired Mac that shared nothing yet is still listed, with its own sentence, and is not "no Macs yet".
    @Test func aPairedMacThatSharedNothingIsListedWithItsOwnSentence() {
        let machines = [PairedMachine(id: "https://a:8765", name: "a", libraries: [])]
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.map(\.machine.name) == ["a"])
        #expect(sections.first?.rows == [.nothingShared("a hasn't shared any project yet")])
    }

    /// No paired Mac, no section: the sidebar draws no "Shared Libraries" heading and no how-to-pair sentence.
    @Test func noPairedMacMeansNoSections() {
        #expect(SharedMachineSections.sections([]).isEmpty)
    }

    @Test func eachPairedMacKeepsItsOwnLibrariesInOrder() {
        let machines = [PairedMachine(id: "https://a:8765", name: "a", libraries: ["/x/One", "/x/Two"]),
                        PairedMachine(id: "https://b:8765", name: "b", libraries: [])]
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.first?.rows == [.library("/x/One"), .library("/x/Two")])
        #expect(sections.count == 2)
    }
}
