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

    @Test("an unknown tool keeps the old selection-based answer")
    func unknownToolFallsBackToSelection() {
        // Older engine, or the registry not loaded yet: guessing would rename
        // the model in a sentence about a paid run.
        #expect(tier(toolStep("not_in_registry")) == .vision)
        let textSelection = WorkflowBarPolicy.defaultTier(
            for: toolStep("not_in_registry"),
            tools: registry,
            visionTier: Self.appleVision,
            selectionPrefersVision: false
        )
        #expect(textSelection == .text)
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
