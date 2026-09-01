import Foundation

// Which model an UNPINNED chain step runs on — decided per STEP, from what
// that step's tool needs, never from what happens to be selected.
//
// The bug this exists for (Daniel, 2026-09-01): with an image selected, the
// bar's sentence read "use apple-vision to Detect Regions → then use
// apple-vision to Transcribe → then use apple-vision to Accounts→Spreadsheet
// (CSV) → then use apple-vision to Translate". Every step had inherited the
// SELECTION's tier. Apple Vision is an OCR pass — it ignores the prompt and
// returns the page's own text — so the CSV and Translate steps could not
// possibly work, and the sentence promised they would.
//
// The selection answers "is there an image here?", which is the wrong
// question for step four. The right question is "what does THIS step's tool
// need?", and the engine already publishes that answer per tool
// (`category`, `requires_generative_model`) and per workflow
// (`requires_vision`). This is a projection of those declarations, kept free
// of SwiftUI so the rule is unit-testable.
extension WorkflowBarPolicy {

    /// The configured default a step resolves to when nothing is pinned.
    enum ModelTier: String, Equatable {
        /// The Vision default — a page read as pixels.
        case vision
        /// The Text default — a prompt answered as language.
        case text
    }

    /// True when this provider/model does RECOGNITION rather than generation.
    ///
    /// The client mirror of the engine's `is_recognition_only_vision_model`
    /// (#4345): Apple's on-device vision route is OCR, so an empty/`default`/
    /// `apple-vision` model on the `apple` provider returns recognized text
    /// and cannot answer a prompt. Mirrored rather than asked over the wire
    /// because it decides what the SENTENCE says, on every keystroke; the
    /// engine stays the enforcement point.
    static func isRecognitionOnlyVisionModel(provider: String, model: String) -> Bool {
        let normalizedProvider = provider.trimmingCharacters(in: .whitespaces).lowercased()
        guard normalizedProvider == "apple" || normalizedProvider == "apple_vision" else {
            return false
        }
        let normalizedModel = model.trimmingCharacters(in: .whitespaces).lowercased()
        return normalizedModel.isEmpty
            || normalizedModel == "default"
            || normalizedModel == "apple-vision"
    }

    /// The registry entry for a tool step, matched the way the rest of the
    /// app matches it — lowercased name.
    static func toolInfo(for step: StagedWorkflowStep, tools: [ToolInfo]) -> ToolInfo? {
        guard case .tool(let name, _, _, _) = step.kind else { return nil }
        let key = name.lowercased()
        return tools.first { $0.name.lowercased() == key }
    }

    /// Whether the step reads PIXELS, as the engine declares it: a workflow
    /// carries the server's `requires_vision` (which descends into child
    /// workflows), a tool carries its category — the same string
    /// `_required_llm_capability` reads on the engine side.
    static func stepReadsPixels(
        _ step: StagedWorkflowStep,
        tools: [ToolInfo],
        selectionPrefersVision: Bool
    ) -> Bool {
        if let workflow = step.workflow { return workflow.requiresVision }
        guard let info = toolInfo(for: step, tools: tools) else {
            // An unknown tool (older engine, registry not loaded yet) keeps
            // the OLD behaviour rather than guessing — a wrong guess here
            // renames the model in a sentence about a paid run.
            return selectionPrefersVision
        }
        return ["vision", "audio", "video"].contains(info.category.lowercased())
    }

    /// Whether the step PARSES the model's answer, so a recognition-only
    /// model can never serve it. Only a tool step can say; a workflow step
    /// fails open (false), leaving the engine's preflight to refuse it.
    static func stepRequiresGenerativeModel(
        _ step: StagedWorkflowStep,
        tools: [ToolInfo]
    ) -> Bool {
        toolInfo(for: step, tools: tools)?.requiresGenerativeModel ?? false
    }

    /// The tier an unpinned step resolves to.
    ///
    /// Two rules, in order:
    ///
    /// 1. A step that does not read pixels takes the TEXT default, whatever
    ///    is selected. Translate on a scanned page is still translation.
    /// 2. A step that reads pixels AND parses the answer takes the TEXT
    ///    default when the configured Vision default is OCR-only — the OCR
    ///    route cannot answer its prompt, so naming it in the sentence would
    ///    promise a run the engine is about to refuse.
    ///
    /// Everything else keeps the Vision default: Transcribe and Detect
    /// Regions are exactly the work Apple Vision is for, and routing them to
    /// a cloud text model would spend money the user never asked to spend.
    static func defaultTier(
        for step: StagedWorkflowStep,
        tools: [ToolInfo],
        visionTier: WorkflowBarModelChoice?,
        selectionPrefersVision: Bool
    ) -> ModelTier {
        guard stepReadsPixels(
            step, tools: tools, selectionPrefersVision: selectionPrefersVision
        ) else {
            return .text
        }
        guard stepRequiresGenerativeModel(step, tools: tools) else { return .vision }
        let visionIsOCROnly = visionTier.map {
            isRecognitionOnlyVisionModel(provider: $0.provider, model: $0.model)
        } ?? true
        return visionIsOCROnly ? .text : .vision
    }

    /// The concrete provider/model an unpinned step resolves to, given the
    /// configured tiers. Falls back to the other tier rather than to nothing:
    /// a user with only one tier configured still gets a named model.
    static func defaultChoice(
        for step: StagedWorkflowStep,
        tools: [ToolInfo],
        textTier: WorkflowBarModelChoice?,
        visionTier: WorkflowBarModelChoice?,
        selectionPrefersVision: Bool
    ) -> WorkflowBarModelChoice? {
        switch defaultTier(
            for: step,
            tools: tools,
            visionTier: visionTier,
            selectionPrefersVision: selectionPrefersVision
        ) {
        case .vision: return visionTier ?? textTier
        case .text:   return textTier ?? visionTier
        }
    }

    /// What an unpinned step must SEND so the run does what the sentence
    /// promised — or nil when it need send nothing.
    ///
    /// Normally nothing: the engine resolves the same tier from the tool's
    /// category, and a silent client-side pin would freeze today's Settings
    /// into tomorrow's run. The exception is rule 2 above — there the engine
    /// would resolve the Vision default (OCR) and refuse the node, while the
    /// bar has already shown a text model's name. Sending it makes display
    /// and execution agree, and makes the step possible rather than merely
    /// honest about failing.
    ///
    /// A PINNED step returns nil too: its own override already rides along.
    /// Restricted to TOOL steps: a workflow is many nodes, and a run-wide
    /// override would drag its genuinely-vision nodes onto a text model.
    static func implicitRunOverride(
        for step: StagedWorkflowStep,
        tools: [ToolInfo],
        textTier: WorkflowBarModelChoice?,
        visionTier: WorkflowBarModelChoice?,
        selectionPrefersVision: Bool
    ) -> WorkflowBarModelChoice? {
        guard !step.hasModelOverride,
              step.isTool,
              stepReadsPixels(
                  step, tools: tools, selectionPrefersVision: selectionPrefersVision
              ),
              stepRequiresGenerativeModel(step, tools: tools),
              defaultTier(
                  for: step,
                  tools: tools,
                  visionTier: visionTier,
                  selectionPrefersVision: selectionPrefersVision
              ) == .text,
              let text = textTier,
              !text.model.isEmpty
        else { return nil }
        return text
    }
}
