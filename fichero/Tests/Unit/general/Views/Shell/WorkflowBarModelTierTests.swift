//
//  WorkflowBarModelTierTests.swift
//  FicheroTests
//
//  The per-step default-model rule (2026-09-01). Daniel staged
//  Detect Regions → Transcribe → Accounts→Spreadsheet (CSV) → Translate on an
//  image and the bar's sentence said "use apple-vision" four times: every step
//  had inherited the SELECTION's tier. Apple Vision is an OCR pass, so the CSV
//  and Translate steps were promised runs they could not make. The rule under
//  test is that a step's default comes from its own tool's declared needs.
//

@testable import Fichero
import Foundation
import Testing

struct WorkflowBarModelTierTests {

    // MARK: - Fixtures

    private static let appleVision = WorkflowBarModelChoice(
        label: "apple-vision  ·  Vision", provider: "apple", model: "apple-vision"
    )
    private static let claude = WorkflowBarModelChoice(
        label: "opus-4-7  ·  Text", provider: "anthropic", model: "claude-opus-4-7"
    )
    private static let visionLLM = WorkflowBarModelChoice(
        label: "gpt-5  ·  Vision", provider: "openai", model: "gpt-5"
    )

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

    private func toolStep(_ name: String) -> StagedWorkflowStep {
        StagedWorkflowStep(
            kind: .tool(name: name, displayName: name, icon: "wrench", usesLLM: true)
        )
    }

    private func workflowStep(
        _ name: String, requiresVision: Bool
    ) -> StagedWorkflowStep {
        StagedWorkflowStep(
            kind: .workflow(
                WorkflowSidebarItem(id: name, name: name, requiresVision: requiresVision)
            )
        )
    }

    private var registry: [ToolInfo] {
        [
            tool("transcribe", category: "vision"),
            tool("detect_regions", category: "vision"),
            tool("table_extract", category: "vision", requiresGenerativeModel: true),
            tool("translate", category: "llm", requiresGenerativeModel: true)
        ]
    }

    private func tier(
        _ step: StagedWorkflowStep,
        vision: WorkflowBarModelChoice? = WorkflowBarModelTierTests.appleVision
    ) -> WorkflowBarPolicy.ModelTier {
        WorkflowBarPolicy.defaultTier(
            for: step,
            tools: registry,
            visionTier: vision,
            // The selection IS an image in every case here — that is exactly
            // the state the bug needed.
            selectionPrefersVision: true
        )
    }

    // MARK: - The rule

    @Test("a text tool takes the Text default even when an image is selected")
    func textToolIgnoresSelectionTier() {
        #expect(tier(toolStep("translate")) == .text)
    }

    @Test("an OCR-capable vision tool keeps the Vision default")
    func visionToolKeepsVisionTier() {
        #expect(tier(toolStep("transcribe")) == .vision)
        #expect(tier(toolStep("detect_regions")) == .vision)
    }

    @Test("a vision tool that parses the answer leaves an OCR-only Vision default")
    func generativeVisionToolLeavesOCRDefault() {
        // Accounts→Spreadsheet: it reads pixels, but it asks for CSV back.
        // Apple Vision would return the page's own text, so the sentence must
        // not name it.
        #expect(tier(toolStep("table_extract")) == .text)
    }

    @Test("…and keeps the Vision default once that default can generate")
    func generativeVisionToolKeepsCapableVisionDefault() {
        #expect(tier(toolStep("table_extract"), vision: Self.visionLLM) == .vision)
    }

    @Test("a workflow step follows the server's requires_vision, not the selection")
    func workflowStepFollowsServerFlag() {
        #expect(tier(workflowStep("Catalogue", requiresVision: false)) == .text)
        #expect(tier(workflowStep("Transcribe", requiresVision: true)) == .vision)
    }

    @Test("an unknown tool is never defaulted onto an OCR-only route")
    func unknownToolIsNeverDefaultedOntoOCR() {
        // Daniel, 2026-09-02: "Cleanup — single small-model pass" resolved to
        // Apple Vision and failed with the engine's own refusal. The tool was
        // not in the client registry, so `requires_generative_model` read
        // false BY ABSENCE and the step inherited the image selection's tier.
        // Absence of the flag is not evidence that the flag is false.
        #expect(tier(toolStep("not_in_registry")) == .text)
        // Nothing is being guessed about the SELECTION: with a text selection
        // the answer was already Text, and it still is.
        let textSelection = WorkflowBarPolicy.defaultTier(
            for: toolStep("not_in_registry"),
            tools: registry,
            visionTier: Self.appleVision,
            selectionPrefersVision: false
        )
        #expect(textSelection == .text)
    }

    @Test("an unknown tool keeps the Vision default once that default can generate")
    func unknownToolKeepsCapableVisionDefault() {
        // The rule excludes NON-GENERATIVE providers, not the vision tier: a
        // vision model that can answer a prompt is still the right default for
        // an image selection, and moving it to the text tier would spend money
        // for nothing.
        #expect(tier(toolStep("not_in_registry"), vision: Self.visionLLM) == .vision)
    }

    @Test("a registry tool that declares no generative need still takes Vision")
    func knownRecognitionToolIsConfirmed() {
        #expect(WorkflowBarPolicy.stepIsConfirmedRecognitionWork(
            toolStep("transcribe"), tools: registry))
        #expect(!WorkflowBarPolicy.stepIsConfirmedRecognitionWork(
            toolStep("table_extract"), tools: registry))
        #expect(!WorkflowBarPolicy.stepIsConfirmedRecognitionWork(
            toolStep("not_in_registry"), tools: registry))
        // A workflow keeps the server's requires_vision as its confirmation —
        // demoting Apple-Vision transcription presets would spend money.
        #expect(WorkflowBarPolicy.stepIsConfirmedRecognitionWork(
            workflowStep("Transcribe", requiresVision: true), tools: registry))
    }

    @Test("a text-tier step never falls back onto the excluded OCR model")
    func textTierNeverFallsBackOntoOCR() {
        // The fallback must not undo the rule that produced it: with no Text
        // tier configured, a generative step names NOTHING rather than naming
        // the very provider the rule excluded.
        let choice = WorkflowBarPolicy.defaultChoice(
            for: toolStep("table_extract"),
            tools: registry,
            textTier: nil,
            visionTier: Self.appleVision,
            selectionPrefersVision: true
        )
        #expect(choice == nil)
        // A vision model that CAN generate is a legitimate fallback.
        let capable = WorkflowBarPolicy.defaultChoice(
            for: toolStep("translate"),
            tools: registry,
            textTier: nil,
            visionTier: Self.visionLLM,
            selectionPrefersVision: true
        )
        #expect(capable?.model == "gpt-5")
    }

    @Test("the run stamps the text model for an unknown tool too")
    func unknownToolRunOverride() {
        // Display and execution answer to one rule: the bar names the text
        // model, so the run must send it — otherwise the engine resolves the
        // Vision default and refuses exactly as it did on 2026-09-02.
        let override = WorkflowBarPolicy.implicitRunOverride(
            for: toolStep("not_in_registry"),
            tools: registry,
            textTier: Self.claude,
            visionTier: Self.appleVision,
            selectionPrefersVision: true
        )
        #expect(override?.model == "claude-opus-4-7")
    }

    // MARK: - Which model that names

    @Test("the resolved choice is the tier's model, per step")
    func resolvedChoicePerStep() {
        func choice(_ step: StagedWorkflowStep) -> WorkflowBarModelChoice? {
            WorkflowBarPolicy.defaultChoice(
                for: step,
                tools: registry,
                textTier: Self.claude,
                visionTier: Self.appleVision,
                selectionPrefersVision: true
            )
        }
        #expect(choice(toolStep("transcribe"))?.model == "apple-vision")
        #expect(choice(toolStep("translate"))?.model == "claude-opus-4-7")
        #expect(choice(toolStep("table_extract"))?.model == "claude-opus-4-7")
    }

    @Test("one configured tier still names a model rather than nothing")
    func singleConfiguredTier() {
        let choice = WorkflowBarPolicy.defaultChoice(
            for: toolStep("transcribe"),
            tools: registry,
            textTier: Self.claude,
            visionTier: nil,
            selectionPrefersVision: true
        )
        #expect(choice?.model == "claude-opus-4-7")
    }

    // MARK: - Recognition-only detection

    @Test("only Apple's OCR route counts as recognition-only")
    func recognitionOnlyDetection() {
        #expect(WorkflowBarPolicy.isRecognitionOnlyVisionModel(
            provider: "apple", model: "apple-vision"))
        #expect(WorkflowBarPolicy.isRecognitionOnlyVisionModel(
            provider: "Apple", model: ""))
        #expect(WorkflowBarPolicy.isRecognitionOnlyVisionModel(
            provider: "apple", model: "default"))
        // Apple Intelligence generates; it is not the OCR route.
        #expect(!WorkflowBarPolicy.isRecognitionOnlyVisionModel(
            provider: "apple", model: "apple-intelligence"))
        #expect(!WorkflowBarPolicy.isRecognitionOnlyVisionModel(
            provider: "openai", model: "gpt-5"))
    }

    // MARK: - What the RUN sends

    @Test("the run stamps the text model only where the engine would disagree")
    func implicitOverrideOnlyWhereNeeded() {
        func override(_ step: StagedWorkflowStep) -> WorkflowBarModelChoice? {
            WorkflowBarPolicy.implicitRunOverride(
                for: step,
                tools: registry,
                textTier: Self.claude,
                visionTier: Self.appleVision,
                selectionPrefersVision: true
            )
        }
        // The engine resolves a vision tool onto the Vision default and would
        // refuse this node; the bar already promised a text model, so the run
        // sends it.
        #expect(override(toolStep("table_extract"))?.model == "claude-opus-4-7")
        // Everywhere else the engine resolves the same tier by itself, and a
        // silent client pin would freeze today's Settings into the chain.
        #expect(override(toolStep("translate")) == nil)
        #expect(override(toolStep("transcribe")) == nil)
        #expect(override(workflowStep("Catalogue", requiresVision: true)) == nil)
    }

    @Test("a pinned step is left exactly as pinned")
    func pinnedStepUntouched() {
        var pinned = toolStep("table_extract")
        pinned.providerOverride = "mlx"
        pinned.modelOverride = "qwen2-vl"
        let override = WorkflowBarPolicy.implicitRunOverride(
            for: pinned,
            tools: registry,
            textTier: Self.claude,
            visionTier: Self.appleVision,
            selectionPrefersVision: true
        )
        #expect(override == nil)
    }
}

/// A step that calls NO model must not have one named for it (Daniel,
/// 2026-09-03): an image-editing chain — rotate, enhance, remove background —
/// is arithmetic on pixels, and the bar's sentence printed a model lozenge per
/// step anyway, claiming a cost and a dependency the run does not have.
struct WorkflowBarModelClaimTests {
    private func tool(_ name: String, usesLLM: Bool) -> ToolInfo {
        ToolInfo(
            name: name,
            displayName: name.capitalized,
            description: "",
            category: usesLLM ? "llm" : "image",
            icon: "wrench",
            color: "blue",
            inputPorts: [],
            outputPorts: [],
            usesLLM: usesLLM,
            supportsBatch: true,
            supportsStreaming: false,
            supportsStructuredOutput: false,
            sortOrder: 0,
            requiresGenerativeModel: false
        )
    }

    private func toolStep(_ name: String, usesLLM: Bool) -> StagedWorkflowStep {
        StagedWorkflowStep(
            kind: .tool(name: name, displayName: name, icon: "wrench", usesLLM: usesLLM)
        )
    }

    private var registry: [ToolInfo] {
        [tool("rotate_image", usesLLM: false),
         tool("enhance_image", usesLLM: false),
         tool("transcribe", usesLLM: true)]
    }

    @Test("an image-editing step claims no model")
    func imageStepsAreModelLess() {
        #expect(
            !WorkflowBarPolicy.stepTakesModel(
                toolStep("rotate_image", usesLLM: false), tools: registry
            )
        )
        #expect(
            !WorkflowBarPolicy.stepTakesModel(
                toolStep("enhance_image", usesLLM: false), tools: registry
            )
        )
    }

    @Test("an LLM step keeps its model token")
    func llmStepsKeepTheirModel() {
        #expect(
            WorkflowBarPolicy.stepTakesModel(
                toolStep("transcribe", usesLLM: true), tools: registry
            )
        )
    }

    @Test("a restored chain's missing flag is confirmed against the registry, not believed")
    func restoreDefaultIsNotEvidence() {
        // WorkflowBarChainPersistence reads `usesLLM = false` for a chain
        // saved before the key existed. Believing it would silently strip the
        // model from a transcription step — a run that DOES cost.
        #expect(
            WorkflowBarPolicy.stepTakesModel(
                toolStep("transcribe", usesLLM: false), tools: registry
            )
        )
    }

    @Test("a tool the registry cannot name keeps its token — absence is not evidence")
    func unknownToolFailsOpen() {
        #expect(
            WorkflowBarPolicy.stepTakesModel(
                toolStep("some_new_tool", usesLLM: false), tools: registry
            )
        )
        #expect(WorkflowBarPolicy.stepTakesModel(toolStep("rotate_image", usesLLM: false), tools: []))
    }

    @Test("a workflow step follows the engine's accepts_model_override")
    func workflowStepsFollowTheEngine() {
        func workflowStep(_ accepts: Bool) -> StagedWorkflowStep {
            StagedWorkflowStep(
                kind: .workflow(
                    WorkflowSidebarItem(name: "Enhance Images", acceptsModelOverride: accepts)
                )
            )
        }
        // "Enhance Images" pins nothing and honours no override: no node in it
        // would use a model.
        #expect(!WorkflowBarPolicy.stepTakesModel(workflowStep(false), tools: registry))
        #expect(WorkflowBarPolicy.stepTakesModel(workflowStep(true), tools: registry))
    }
}

/// The sentence itself: a model-less step reads "…, then Rotate Images", with
/// no "use [model] to" and no lozenge. Pinned against the source because the
/// rail is a SwiftUI view the test process cannot instantiate.
struct WorkflowBarSentenceShapeTests {
    @Test("the rail only says 'use … to' for a step that takes a model")
    func railGuardsTheModelPhrase() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Shell/Toolbar/WorkflowBar+ChainRail.swift")
        let rail = try String(contentsOf: url, encoding: .utf8)
        #expect(rail.contains("if stepTakesModel(step) {"))
        #expect(rail.contains("modelToken(for: step, at: index)"))
        // The connective survives without the claim.
        #expect(rail.contains("} else if index > 0 {"))
        // Exactly one model token in the sentence, inside that guard.
        #expect(rail.components(separatedBy: "modelToken(for: step").count == 2)
    }

    @Test("the per-step menu offers no models for a step that runs none")
    func menuDoesNotImplyAModel() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Shell/Toolbar/WorkflowBar.swift")
        let bar = try String(contentsOf: url, encoding: .utf8)
        #expect(bar.contains("!stepTakesModel(staged[index])"))
        #expect(bar.contains("runs no model"))
    }
}
