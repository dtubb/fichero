//
//  SharedLibraryChooserIOSTests.swift
//  FicheroTests
//
//  sharing.ios.shared-library-chooser / sharing.ios.no-empty-detail (#5396): the phone's chooser lists only the
//  libraries shared with this person, and with none it says how to pair instead of showing an empty screen.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct SharedLibraryChooserIOSTests {
    @Test func noPairedMacSaysHowToPair() {
        #expect(SharedLibraryChooserView.showsHowToPair([]))
    }

    /// #6459: a paired Mac that shared nothing yet is still listed, with its own sentence, and is not "no Macs yet".
    @Test func aPairedMacThatSharedNothingIsListedWithItsOwnSentence() {
        let machines = [PairedMachine(id: "https://a:8765", name: "a", libraries: [])]
        #expect(!SharedLibraryChooserView.showsHowToPair(machines))
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.map(\.machine.name) == ["a"])
        #expect(sections.first?.rows == [.nothingShared("a hasn't shared any project yet")])
    }

    @Test func eachPairedMacKeepsItsOwnLibrariesInOrder() {
        let machines = [PairedMachine(id: "https://a:8765", name: "a", libraries: ["/x/One", "/x/Two"]),
                        PairedMachine(id: "https://b:8765", name: "b", libraries: [])]
        let sections = SharedMachineSections.sections(machines)
        #expect(sections.first?.rows == [.library("/x/One"), .library("/x/Two")])
        #expect(sections.count == 2)
    }

    @Test func aSharedLibraryIsListedNotTheHowToSentence() {
        let machine = PairedMachine(id: "https://a:8765", name: "a", libraries: ["/x/Marshall"])
        #expect(!SharedLibraryChooserView.showsHowToPair([machine]))
    }
}
