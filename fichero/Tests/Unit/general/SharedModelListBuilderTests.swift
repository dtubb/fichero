//
//  SharedModelListBuilderTests.swift
//  FicheroTests
//
//  The ONE pure builder that every model picker will share
//  (docs/contributor_manual/specs/ui/model-selector-consistency.md, RATIFIED
//  2026-09-15). Extracted from the workflow bar's `pinnableModels`, which is
//  the builder the spec adopts, so these guard the exact behaviour the
//  surfaces converge on:
//
//    - the configured tiers lead the list, annotated with their tier;
//    - dedupe is on provider+model, never model alone (a router call and a
//      direct call are two prices);
//    - vision is a tri-state read from the catalog — a definite false, else
//      the provider default, else nil (unknown is NOT "no", 2026-09-01);
//    - an empty provider cache falls back to the tiers, never to nothing.
//

@testable import Fichero
import Foundation
import Testing

struct SharedModelListBuilderTests {

    // MARK: - Fixtures

    private func provider(
        _ id: String, models: [String], vision: Bool,
        details: [LLMProviderModelDetail] = []
    ) -> LLMProvider {
        LLMProvider(
            id: id, name: id, models: models, available: true,
            supportsVision: vision, modelDetails: details
        )
    }

    private let visionTier = SharedModelListBuilder.TierDefault(
        tier: "Vision", provider: "apple", model: "apple-vision"
    )
    private let textTier = SharedModelListBuilder.TierDefault(
        tier: "Text", provider: "anthropic", model: "claude-opus-5"
    )

    // MARK: - The list is every configured model, never just the tiers

    @Test("Every configured model is offered, not just the tier defaults")
    func everyConfiguredModelIsOffered() {
        let choices = SharedModelListBuilder.build(
            providers: [
                provider("anthropic", models: ["claude-opus-5", "claude-haiku-5"], vision: true),
                provider("google", models: ["gemini-flash-lite"], vision: true),
                provider("apple", models: ["apple-vision"], vision: true)
            ],
            tierDefaults: [visionTier, textTier]
        )

        #expect(
            choices.count == 4,
            "four configured models across three providers must all appear"
        )
        #expect(Set(choices.map(\.model)) == [
            "apple-vision", "claude-opus-5", "claude-haiku-5", "gemini-flash-lite"
        ])
    }

    // MARK: - Tier-first order

    @Test("The configured tiers come first, annotated with their tier")
    func tiersLeadTheList() {
        let choices = SharedModelListBuilder.build(
            providers: [provider("anthropic", models: ["claude-haiku-5", "claude-opus-5"], vision: true)],
            tierDefaults: [textTier]
        )

        #expect(choices.first?.model == "claude-opus-5", "the Text tier default leads")
        #expect(choices.first?.tier == "Text")
        #expect(choices.count == 2, "the tier row must not duplicate its catalog row")
        // The tail is alphabetical within its provider, tier-annotation gone.
        #expect(choices.last?.model == "claude-haiku-5")
        #expect(choices.last?.tier == nil)
    }

    @Test("Providers are grouped and sorted, tiers still ahead of everything")
    func providerGroupedAndSorted() {
        let choices = SharedModelListBuilder.build(
            providers: [
                provider("anthropic", models: ["claude-opus-5", "claude-haiku-5"], vision: true)
            ],
            tierDefaults: [textTier]
        )
        // opus (tier) first, then the remaining models alphabetically.
        #expect(choices.map(\.model) == ["claude-opus-5", "claude-haiku-5"])
    }

    // MARK: - Dedupe on provider+model, never model alone

    @Test("The same model id under two providers is two rows")
    func providerPlusModelDedupe() {
        let choices = SharedModelListBuilder.build(
            providers: [
                provider("anthropic", models: ["claude-opus-5"], vision: true),
                provider("openrouter", models: ["claude-opus-5"], vision: true)
            ],
            tierDefaults: []
        )
        #expect(
            choices.count == 2,
            "a router call and a direct call are two prices — never collapsed"
        )
        #expect(Set(choices.map(\.provider)) == ["anthropic", "openrouter"])
    }

    @Test("A tier and its own catalog row do not duplicate")
    func tierDoesNotDuplicateItsCatalogRow() {
        let choices = SharedModelListBuilder.build(
            providers: [provider("anthropic", models: ["claude-opus-5"], vision: true)],
            tierDefaults: [textTier]
        )
        #expect(choices.count == 1)
        #expect(choices.first?.tier == "Text", "the tier annotation wins for the shared row")
    }

    // MARK: - Vision is tri-state, never a filter

    @Test("A definite catalog false is reported, never hides the row")
    func definiteVisionFalseIsKeptAndMarked() {
        let choices = SharedModelListBuilder.build(
            providers: [
                provider(
                    "someco", models: ["text-only-5"], vision: true,
                    details: [LLMProviderModelDetail(modelId: "text-only-5", supportsVision: false)]
                )
            ],
            tierDefaults: []
        )
        #expect(choices.count == 1, "a text-only model is marked, never removed")
        #expect(choices.first?.supportsVision == false)
    }

    @Test("A model absent from modelDetails inherits the provider vision flag")
    func modelInheritsProviderVisionFlag() {
        let choices = SharedModelListBuilder.build(
            providers: [provider("google", models: ["gemini-flash-lite"], vision: true)],
            tierDefaults: []
        )
        #expect(choices.first?.supportsVision == true)
    }

    @Test("A model no provider describes has an unknown vision flag, not false")
    func unknownProviderVisionIsNil() {
        // The tier names a model whose provider is not in the cache at all.
        let choices = SharedModelListBuilder.build(
            providers: [],
            tierDefaults: [textTier]
        )
        #expect(choices.count == 1, "an empty cache must not empty the list")
        #expect(
            choices[0].supportsVision == nil,
            "absence of a catalog row is not a statement that the model lacks vision"
        )
    }

    // MARK: - Tiers-only fallback when the provider cache is empty

    @Test("An empty provider cache falls back to the tiers alone")
    func emptyCacheFallsBackToTiers() {
        let choices = SharedModelListBuilder.build(
            providers: [],
            tierDefaults: [visionTier, textTier]
        )
        #expect(choices.count == 2, "the list is never emptier than before the fetch")
        #expect(choices.map(\.model) == ["apple-vision", "claude-opus-5"])
        #expect(choices.map(\.tier) == ["Vision", "Text"])
    }

    @Test("No providers and no tiers yields an empty list, not a crash")
    func nothingConfiguredIsEmpty() {
        #expect(SharedModelListBuilder.build(providers: [], tierDefaults: []).isEmpty)
    }

    // MARK: - Housekeeping the shared row relies on

    @Test("Blank model ids are dropped")
    func blankModelsDropped() {
        let choices = SharedModelListBuilder.build(
            providers: [provider("anthropic", models: ["", "  ", "claude-opus-5"], vision: true)],
            tierDefaults: []
        )
        #expect(choices.map(\.model) == ["claude-opus-5"])
    }

    @Test("displayName is the shortened model id the row shows")
    func displayNameIsShortened() {
        let choices = SharedModelListBuilder.build(
            providers: [provider("openrouter", models: ["openrouter/anthropic/claude-sonnet-5"], vision: true)],
            tierDefaults: []
        )
        #expect(choices.first?.displayName == "claude-sonnet-5")
        #expect(choices.first?.model == "openrouter/anthropic/claude-sonnet-5",
                "the full id survives for the family mark and the pin")
    }
}
