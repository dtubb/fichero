//
//  OwnEngineOfferTests.swift
//  FicheroTests
//
//  #6418: a host the person set that does not answer must offer this Mac's own engine, in words, instead of a dead window.
//

@testable import Fichero
import Foundation
import Testing

struct OwnEngineOfferTests {
    @Test func onlyAMacDialingAnotherMachineOffersItsOwnEngine() {
        #expect(ConnectionPresentation.offersOwnEngine(ownership: .remote, isMacOS: true))
        #expect(!ConnectionPresentation.offersOwnEngine(ownership: .remote, isMacOS: false))
        #expect(!ConnectionPresentation.offersOwnEngine(ownership: .appManaged, isMacOS: true))
        #expect(!ConnectionPresentation.offersOwnEngine(ownership: .externalLocal, isMacOS: true))
    }

    @Test func theSentenceNamesTheMacThatDidNotAnswer() {
        let sentence = ConnectionPresentation.ownEngineSentence(host: "https://air.example:8765")
        #expect(sentence.contains("air.example"))
        #expect(sentence.contains("own engine"))
    }

    @Test func forgettingTheHostAlsoForgetsWhichMacWasChosen() {
        let defaults = EngineConfig.defaults
        let saved = (defaults.string(forKey: EngineConfig.userDefaultsKey), defaults.string(forKey: EngineConfig.wholeMacHostKey))
        defer {
            defaults.set(saved.0, forKey: EngineConfig.userDefaultsKey)
            defaults.set(saved.1, forKey: EngineConfig.wholeMacHostKey)
        }
        EngineConfig.storeHost("https://air.example:8765")
        defaults.set("https://air.example:8765", forKey: EngineConfig.wholeMacHostKey)
        EngineConfig.clearStoredHost()
        #expect(defaults.string(forKey: EngineConfig.userDefaultsKey) == nil)
        #expect(defaults.string(forKey: EngineConfig.wholeMacHostKey) == nil)
    }
}
