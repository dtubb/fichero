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

    @Test func aPairedMacThatSharedNothingSaysHowToPair() {
        #expect(SharedLibraryChooserView.showsHowToPair([PairedMachine(id: "https://a:8765", name: "a", libraries: [])]))
    }

    @Test func aSharedLibraryIsListedNotTheHowToSentence() {
        let machine = PairedMachine(id: "https://a:8765", name: "a", libraries: ["/x/Marshall"])
        #expect(!SharedLibraryChooserView.showsHowToPair([machine]))
    }
}
