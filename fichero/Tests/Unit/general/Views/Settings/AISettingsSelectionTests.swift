//
//  AISettingsSelectionTests.swift
//  FicheroTests
//
//  Ship blocker (2026-09-17): `loadModelsResettingSelection` used to blank the
//  selection synchronously on provider change, then auto-pick `list.first` if
//  the saved model was absent — a fetch failure left "" persisted with only a
//  log line, silently losing the user's pick. The fix's decision (never
//  substitute a different model; keep `current` whatever the fetch returns)
//  is extracted into `selectionAfterModelLoad` so it is a pure, pinned target
//  rather than folded into the async fetch. This guards regression back to
//  the old auto-pick / blank-on-failure behaviour.
//

@testable import Fichero
import Foundation
import Testing

struct AISettingsSelectionTests {

    private func model(_ id: String) -> ModelInfo {
        ModelInfo(
            modelId: id, fullName: id, description: nil,
            isRecommended: false, isLocal: false,
            inputCostPerMillion: 0, outputCostPerMillion: 0,
            batchInputCostPerMillion: nil, batchOutputCostPerMillion: nil,
            cacheReadCostPerMillion: nil,
            maxInputTokens: nil, maxOutputTokens: nil, mode: nil,
            supportsVision: false, supportsFunctionCalling: false,
            supportsAudioInput: false, supportsAudioOutput: false,
            supportsPdfInput: false, supportsPromptCaching: false,
            supportsReasoning: false, supportsWebSearch: false,
            supportsStreaming: false, supportsBatchApi: false,
            provider: "anthropic"
        )
    }

    @Test("A fetch failure leaves the prior model untouched")
    func fetchFailureKeepsPriorSelection() {
        // The caller never calls this on a failure path (the catch block
        // leaves the selection alone entirely) — this pins that "no list" is
        // never grounds to change the selection either.
        let result = AISettingsView.selectionAfterModelLoad(
            current: "claude-sonnet-5", loadedModels: []
        )
        #expect(result == "claude-sonnet-5")
    }

    @Test("A model absent from the freshly-loaded list is not replaced")
    func absentModelIsNotReplaced() {
        let result = AISettingsView.selectionAfterModelLoad(
            current: "claude-sonnet-5",
            loadedModels: [model("claude-opus-5"), model("claude-haiku-5")]
        )
        #expect(
            result == "claude-sonnet-5",
            "an absent model must never be silently swapped for list.first"
        )
    }

    @Test("A model present in the freshly-loaded list is also left as-is")
    func presentModelIsUnchanged() {
        let result = AISettingsView.selectionAfterModelLoad(
            current: "claude-opus-5",
            loadedModels: [model("claude-opus-5"), model("claude-haiku-5")]
        )
        #expect(result == "claude-opus-5")
    }

    @Test("An empty prior selection stays empty — no auto-pick on first load")
    func emptySelectionStaysEmpty() {
        let result = AISettingsView.selectionAfterModelLoad(
            current: "",
            loadedModels: [model("claude-opus-5")]
        )
        #expect(result == "", "the picker, not the loader, is where a first choice is made")
    }
}
