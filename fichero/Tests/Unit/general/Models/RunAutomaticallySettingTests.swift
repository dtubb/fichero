//
//  RunAutomaticallySettingTests.swift
//  FicheroTests
//
//  #6441 `activity.automatic.one-place`, `activity.pane.run-automatically-is-a-setting`: the one switch's mapping to the
//  engine's mode, and its words.
//

@testable import Fichero
import Foundation
import Testing

struct RunAutomaticallySettingTests {
    @Test("on is automatic, off pauses; the one-off Run Now still reads as on; never set as the mode")
    func mapping() {
        #expect(RunAutomaticallySetting.mode(isOn: true) == .automatic)
        #expect(RunAutomaticallySetting.mode(isOn: false) == .paused)
        #expect(RunAutomaticallySetting.isOn(.automatic) && RunAutomaticallySetting.isOn(.started))
        #expect(!RunAutomaticallySetting.isOn(.paused))
    }

    @Test("a plain label and one sentence, no mode words")
    func words() {
        #expect(RunAutomaticallySetting.label == "Run automatically")
        let sentences = RunAutomaticallySetting.sentence.split(separator: ".").filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        #expect(sentences.count == 1)
        #expect(!RunAutomaticallySetting.sentence.contains("Run Now"))
    }
}
