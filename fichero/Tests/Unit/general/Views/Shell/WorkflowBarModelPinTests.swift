//
//  WorkflowBarModelPinTests.swift
//  FicheroTests
//
//  WHICH models the per-step menu offers, and WHICH model the sentence
//  promises (R-11, Daniel 2026-09-04).
//
//  Two complaints, one rule. "Workflow not letting us see all models, just
//  showing 2 — is it filtering by vision when it should use text?" — the menu
//  was offering the four Settings tiers, which dedupe to two. And "the model
//  chosen is not the model used" — a pin the step's tool cannot serve was
//  shown as though it would run, while the engine resolved something else.
//
//  Precedence under test: step pin > run-level choice > tier default, with
//  capability-compatibility as the qualifier — and NEVER a filter: a model
//  that cannot serve a step is marked with a reason, never hidden.
//

@testable import Fichero
import Foundation
import Testing

struct WorkflowBarModelPinTests {

    // MARK: - Fixtures

    private func tool(
        _ name: String,
        category: String,
        requiresGenerativeModel: Bool = false
    ) -> ToolInfo {
        ToolInfo(
            name: name,
            displayName: name.capitalized,
            description: "",
            category: category,
            icon: "wrench",
            color: "blue",
            inputPorts: [],
            outputPorts: [],
            usesLLM: true,
            supportsBatch: true,
            supportsStreaming: false,
            supportsStructuredOutput: false,
            sortOrder: 0,
            requiresGenerativeModel: requiresGenerativeModel
        )
    }

    private var registry: [ToolInfo] {
        [
            tool("transcribe", category: "vision"),
            tool("table_extract", category: "vision", requiresGenerativeModel: true),
            tool("translate", category: "llm", requiresGenerativeModel: true)
        ]
    }

    private func step(_ name: String, pinnedTo model: String? = nil,
                      provider: String = "") -> StagedWorkflowStep {
        var step = StagedWorkflowStep(
            kind: .tool(name: name, displayName: name, icon: "wrench", usesLLM: true)
        )
        step.modelOverride = model
        step.providerOverride = model == nil ? nil : provider
        return step
    }

    private func choice(
        _ model: String, provider: String, vision: Bool? = nil
    ) -> WorkflowBarModelChoice {
        WorkflowBarModelChoice(
            label: model, provider: provider, model: model, supportsVision: vision
        )
    }

    private func provider(
        _ id: String, models: [String], vision: Bool,
        details: [LLMProviderModelDetail] = []
    ) -> LLMProvider {
        LLMProvider(
            id: id, name: id, models: models, available: true,
            supportsVision: vision, modelDetails: details
        )
    }

    private let appleVisionTier = WorkflowBarPolicy.TierDefault(
        tier: "Vision", provider: "apple", model: "apple-vision"
    )
    private let textTier = WorkflowBarPolicy.TierDefault(
        tier: "Text", provider: "anthropic", model: "claude-opus-5"
    )

    // MARK: - The list is every configured model, never two

    @Test("Every configured model is pinnable, not just the tier defaults")
    func everyConfiguredModelIsOffered() {
        let choices = WorkflowBarPolicy.pinnableModels(
            providers: [
                provider("anthropic", models: ["claude-opus-5", "claude-haiku-5"], vision: true),
                provider("google", models: ["gemini-flash-lite"], vision: true),
                provider("apple", models: ["apple-vision"], vision: true)
            ],
            tierDefaults: [appleVisionTier, textTier]
        )

        #expect(
            choices.count == 4,
            """
            the menu offered the deduped tier defaults — two rows for a user \
            with four configured models (Daniel, 2026-09-04)
            """
        )
        #expect(Set(choices.map(\.model)) == [
            "apple-vision", "claude-opus-5", "claude-haiku-5", "gemini-flash-lite"
        ])
    }

    @Test("The configured tiers come first, annotated with their tier")
    func tiersLeadTheList() {
        let choices = WorkflowBarPolicy.pinnableModels(
            providers: [provider("anthropic", models: ["claude-haiku-5", "claude-opus-5"], vision: true)],
            tierDefaults: [textTier]
        )

        #expect(choices.first?.model == "claude-opus-5", "the Text tier default leads")
        #expect(choices.first?.tier == "Text")
        #expect(choices.first?.label.hasSuffix("Text") == true)
        #expect(choices.count == 2, "the tier row must not duplicate its catalog row")
    }

    @Test("A model the catalog does not describe is still offered, with no vision claim")
    func unknownProviderStillOffered() {
        let choices = WorkflowBarPolicy.pinnableModels(
            providers: [],
            tierDefaults: [textTier]
        )

        #expect(choices.count == 1, "an empty cache must not empty the menu")
        #expect(
            choices[0].supportsVision == nil,
            "absence of a catalog row is not a statement that the model lacks vision"
        )
    }

    // MARK: - Marked, never filtered

    @Test("A text-only model on a vision step is offered with a reason, not hidden")
    func textOnlyModelIsMarkedOnAVisionStep() {
        let reason = WorkflowBarPolicy.modelUnsuitableReason(
            choice("text-only-5", provider: "someco", vision: false),
            for: step("transcribe"),
            tools: registry,
            selectionPrefersVision: true
        )

        #expect(reason != nil, "a text-only model must be marked on a vision step")
        #expect(
            reason?.contains("text-only-5") == true,
            """
            the reason must name the model — a refusal that does not say which \
            model it is about cannot be argued with
            """
        )
    }

    @Test("A model with no vision flag stays pickable — unknown is not 'no'")
    func unknownVisionFlagIsPickable() {
        #expect(
            WorkflowBarPolicy.modelUnsuitableReason(
                choice("brand-new-model", provider: "someco"),
                for: step("transcribe"),
                tools: registry,
                selectionPrefersVision: true
            ) == nil,
            "a model newer than the catalog was disqualified by a missing flag"
        )
    }

    @Test("A vision model on a TEXT step is offered — vision models read text too")
    func visionModelOnTextStepIsFine() {
        #expect(
            WorkflowBarPolicy.modelUnsuitableReason(
                choice("claude-opus-5", provider: "anthropic", vision: true),
                for: step("translate"),
                tools: registry,
                selectionPrefersVision: true
            ) == nil,
            "filtering the pin list by vision is what hid the models Daniel wanted"
        )
    }

    @Test("Apple Vision is marked on a text step — OCR cannot answer a prompt")
    func recognitionOnlyModelIsMarkedOnATextStep() {
        let reason = WorkflowBarPolicy.modelUnsuitableReason(
            choice("apple-vision", provider: "apple", vision: true),
            for: step("translate"),
            tools: registry,
            selectionPrefersVision: true
        )
        #expect(reason != nil, "the 2026-09-01 rule: never claim OCR will Translate")
    }

    @Test("Apple Vision is marked on a vision step that PARSES the answer")
    func recognitionOnlyModelIsMarkedOnAGenerativeVisionStep() {
        #expect(
            WorkflowBarPolicy.modelUnsuitableReason(
                choice("apple-vision", provider: "apple", vision: true),
                for: step("table_extract"),
                tools: registry,
                selectionPrefersVision: true
            ) != nil,
            "table_extract declares requires_generative_model; OCR ignores the prompt"
        )
    }

    @Test("Apple Vision stays pickable for plain recognition work")
    func recognitionOnlyModelServesTranscribe() {
        #expect(
            WorkflowBarPolicy.modelUnsuitableReason(
                choice("apple-vision", provider: "apple", vision: true),
                for: step("transcribe"),
                tools: registry,
                selectionPrefersVision: true
            ) == nil,
            "Transcribe is exactly the work Apple Vision is for"
        )
    }

    // MARK: - A CHAIN's steps take the bar's model too (Daniel, 2026-09-05)

    private func preset(
        _ name: String, requiresVision: Bool = false, accepts: Bool = true
    ) -> StagedWorkflowStep {
        StagedWorkflowStep(
            kind: .workflow(WorkflowSidebarItem(
                id: name, name: name, description: nil,
                nodeCount: 1, edgeCount: 0, isEnabled: true,
                folderPath: "/Extract", sortOrder: 10, isSystem: true,
                isUntested: false, isDirectlyRunnable: true,
                acceptsModelOverride: accepts,
                createdAt: Date(), updatedAt: Date(),
                requiresVision: requiresVision
            ))
        )
    }

    @Test("every step of a five-step chain runs the model the bar names")
    func everyChainStepTakesTheBarsModel() {
        // Daniel, 2026-09-05, on the released build: a five-workflow chain
        // over a 90-image folder with the bar reading claude-sonnet-latest,
        // and "Step 'Extract entities' failed: Apple Intelligence". The bar
        // said one model; a step ran another.
        //
        // The mechanism is in the presets: twelve shipped nodes carry
        // `provider_name: "$small"`, a SIZE-CLASS alias. With no run-level
        // choice on the request those nodes resolve $small from the app's
        // defaults — which seed to Apple — so the step picks its own model
        // exactly as Daniel suspected ("not choosing its own based on
        // defaults or large, small"). The choice never left the app because
        // the override was restricted to a chain of ONE.
        let chain = [
            preset("Detect Regions", requiresVision: true),
            preset("Transcribe", requiresVision: true),
            preset("Extract entities"),
            preset("Extract SVO"),
            preset("Catalogue")
        ]
        let sonnet = choice("claude-sonnet-latest", provider: "anthropic", vision: true)

        for step in chain {
            let sent = WorkflowBarPolicy.workflowStepPickerOverride(
                for: step,
                stagedCount: chain.count,
                tools: registry,
                textTier: sonnet,
                visionTier: sonnet,
                selectionPrefersVision: true
            )
            #expect(
                sent?.model == "claude-sonnet-latest",
                "step '\(step.name)' sent \(sent?.model ?? "NOTHING") — a step "
                    + "that sends nothing resolves its own $small alias and "
                    + "lands on Apple against an explicit cloud choice"
            )
        }
    }

    @Test("a vision step in a mixed chain still takes the VISION tier")
    func aChainRespectsPerStepCapability() {
        // The 2026-09-01 rule survives the fix: spreading a DELIBERATE choice
        // across a chain is right, spreading one tier over every step is not.
        let visionTier = choice("apple-vision", provider: "apple", vision: true)
        let textTier = choice("claude-sonnet-latest", provider: "anthropic", vision: true)

        let readsPixels = WorkflowBarPolicy.workflowStepPickerOverride(
            for: preset("Transcribe", requiresVision: true),
            stagedCount: 3,
            tools: registry,
            textTier: textTier,
            visionTier: visionTier,
            selectionPrefersVision: true
        )
        let readsText = WorkflowBarPolicy.workflowStepPickerOverride(
            for: preset("Extract entities"),
            stagedCount: 3,
            tools: registry,
            textTier: textTier,
            visionTier: visionTier,
            selectionPrefersVision: true
        )

        #expect(readsPixels?.model == "apple-vision")
        #expect(
            readsText?.model == "claude-sonnet-latest",
            "an OCR route must never be sent to do entity extraction"
        )
    }

    @Test("a preset that refuses overrides is still never overridden in a chain")
    func aDeclaredPinSurvivesTheChainFix() {
        #expect(WorkflowBarPolicy.workflowStepPickerOverride(
            for: preset("Locked", accepts: false),
            stagedCount: 5,
            tools: registry,
            textTier: choice("claude-sonnet-latest", provider: "anthropic"),
            visionTier: choice("claude-sonnet-latest", provider: "anthropic"),
            selectionPrefersVision: false
        ) == nil)
    }

    // MARK: - The sentence names what will REALLY run

    @Test("A usable pin is what the sentence shows")
    func honoredPinIsShown() {
        let resolved = WorkflowBarPolicy.effectiveChoice(
            for: step("transcribe", pinnedTo: "claude-opus-5", provider: "anthropic"),
            tools: registry,
            textTier: choice("claude-opus-5", provider: "anthropic"),
            visionTier: choice("apple-vision", provider: "apple"),
            selectionPrefersVision: true
        )
        #expect(resolved?.model == "claude-opus-5")
    }

    @Test("An unusable pin falls to the tier default — the model that will run")
    func unusablePinFallsToTheTierDefault() {
        let resolved = WorkflowBarPolicy.effectiveChoice(
            for: step("translate", pinnedTo: "apple-vision", provider: "apple"),
            tools: registry,
            textTier: choice("claude-opus-5", provider: "anthropic"),
            visionTier: choice("apple-vision", provider: "apple"),
            selectionPrefersVision: true
        )
        #expect(
            resolved?.model == "claude-opus-5",
            """
            the sentence promised a model the engine would decline to use — \
            'the model chosen is not the model used' (Daniel, 2026-09-04)
            """
        )
    }

    @Test("An unpinned step still resolves its own tier default")
    func unpinnedStepResolvesItsTier() {
        let resolved = WorkflowBarPolicy.effectiveChoice(
            for: step("transcribe"),
            tools: registry,
            textTier: choice("claude-opus-5", provider: "anthropic"),
            visionTier: choice("apple-vision", provider: "apple"),
            selectionPrefersVision: true
        )
        #expect(resolved?.model == "apple-vision")
    }
}
