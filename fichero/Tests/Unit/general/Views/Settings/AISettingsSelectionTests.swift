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

    // MARK: - SF7 review finding: the pure function alone doesn't guard the real bug

    /// Every test above only exercises `selectionAfterModelLoad` in isolation — an identity
    /// function, since the whole point of the ship-blocker fix is "never change it". That means
    /// all four would keep passing even if `loadModelsResettingSelection` stopped CALLING it and
    /// reinstated the old `list.first` auto-pick INLINE at the assignment site instead — the exact
    /// regression this file exists to prevent. This is the missing half: a source guardrail that
    /// the production call site routes the selection assignment SOLELY through the pinned pure
    /// function, and never through a reinstated `list.first`/`.first` substitution.
    @Test("loadModelsResettingSelection assigns the selection ONLY via selectionAfterModelLoad")
    func productionCallSiteRoutesOnlyThroughThePureFunction() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Settings/AI/AISettingsView+Helpers.swift"),
            encoding: .utf8
        )
        let body = try Self.functionBody(named: "loadModelsResettingSelection", in: source)
        #expect(
            body.contains("selection.wrappedValue = Self.selectionAfterModelLoad("),
            "the ONLY assignment to `selection` must be the pinned pure function's result"
        )
        #expect(
            !body.contains("list.first"),
            "an inline `list.first` here is exactly the ship-blocker auto-pick regression"
        )
        #expect(
            !body.contains("models.wrappedValue.first"),
            "an inline auto-pick off the freshly-loaded models is the same regression by another name"
        )
    }

    /// Extracts one function's body by brace-counting from its declaration line — good enough for
    /// a single, non-nested top-level function in a known file; not a general Swift parser.
    private static func functionBody(named name: String, in source: String) throws -> String {
        guard let declRange = source.range(of: "func \(name)(") else {
            throw TestSetupError.markerNotFound("func \(name)(")
        }
        guard let openBrace = source[declRange.upperBound...].firstIndex(of: "{") else {
            throw TestSetupError.markerNotFound("{ after func \(name)(")
        }
        var depth = 0
        var index = openBrace
        while index < source.endIndex {
            if source[index] == "{" { depth += 1 }
            if source[index] == "}" {
                depth -= 1
                if depth == 0 {
                    return String(source[openBrace...index])
                }
            }
            index = source.index(after: index)
        }
        throw TestSetupError.markerNotFound("closing brace for func \(name)(")
    }

    private enum TestSetupError: Error {
        case markerNotFound(String)
    }
}
