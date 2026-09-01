import Foundation

/// Maps the workflow bar's staged chain onto the engine's chain store, both
/// ways (2026-08-30, workflow-bar review ruling: the staged chain rides
/// ChainService instead of a per-window @State loop).
///
/// One SHARED chain, named `Workflow Bar`, for the whole library: the point of
/// persisting is that the chain survives window close/reopen and is the same
/// assembly in every window — a per-window copy would resurrect exactly the
/// isolation this migration removes.
///
/// All functions are pure so the mapping is testable without an engine.
enum WorkflowBarChainPersistence {

    /// The one chain the bar owns. Found by name on restore, created on the
    /// first staging if absent.
    static let chainName = "Workflow Bar"

    // A tool step has no workflow until a run realises one (see
    // `resolveWorkflowId(for:)`), so its identity rides in static_inputs —
    // free-form by contract, ignored by the engine, read back on restore.
    private static let kindKey = "staged_kind"
    private static let toolKind = "tool"
    private static let toolNameKey = "staged_tool_name"
    private static let toolDisplayKey = "staged_tool_display"
    private static let toolIconKey = "staged_tool_icon"
    private static let toolUsesLLMKey = "staged_tool_uses_llm"

    /// The staged rail as engine chain steps.
    ///
    /// `resolvedWorkflowIds` (staged step id → workflow id) fills in the
    /// workflow a run just realised for a tool step; the tool marker is kept
    /// alongside so a later restore still shows a tool chip, not a mystery
    /// one-step workflow.
    /// `modelOverrides` (staged step id → provider/model) is what the RUN
    /// stamps for a step the bar resolved to a different tier than the engine
    /// would (2026-09-01). Empty while merely staging, so an idle rail is
    /// never persisted with today's Settings frozen into it.
    static func chainSteps(
        from staged: [StagedWorkflowStep],
        resolvedWorkflowIds: [UUID: String] = [:],
        modelOverrides: [UUID: WorkflowBarModelChoice] = [:]
    ) -> [ChainStep] {
        staged.map { step in
            var staticInputs: [String: AnyCodableValue] = [:]
            let workflowId: String
            switch step.kind {
            case .workflow(let item):
                workflowId = item.id
            case .tool(let name, let displayName, let icon, let usesLLM):
                workflowId = resolvedWorkflowIds[step.id] ?? ""
                staticInputs[kindKey] = .string(toolKind)
                staticInputs[toolNameKey] = .string(name)
                staticInputs[toolDisplayKey] = .string(displayName)
                staticInputs[toolIconKey] = .string(icon)
                staticInputs[toolUsesLLMKey] = .bool(usesLLM)
            }
            let stamped = modelOverrides[step.id]
            return ChainStep(
                id: step.id.uuidString,
                workflowId: workflowId,
                name: step.name,
                staticInputs: staticInputs,
                providerOverride: step.providerOverride ?? stamped?.provider,
                modelOverride: step.modelOverride ?? stamped?.model
            )
        }
    }

    /// A persisted chain back onto the rail.
    ///
    /// A workflow step whose workflow no longer exists is DROPPED, not shown
    /// as a chip that cannot run — the workflow was deleted since the chain
    /// was staged, and resurrecting it would promise a run the engine must
    /// refuse. Chip identity (UUID) is fresh per session by design.
    static func stagedSteps(
        from chain: WorkflowChain,
        workflows: [WorkflowSidebarItem]
    ) -> [StagedWorkflowStep] {
        chain.steps.compactMap { step in
            let kind: StagedStepKind
            var isToolStep = false
            if case .string(let kindValue)? = step.staticInputs[kindKey],
               kindValue == toolKind {
                isToolStep = true
            }
            if isToolStep {
                guard case .string(let name)? = step.staticInputs[toolNameKey],
                      case .string(let display)? = step.staticInputs[toolDisplayKey]
                else { return nil }
                var icon = "wrench"
                if case .string(let stored)? = step.staticInputs[toolIconKey] {
                    icon = stored
                }
                var usesLLM = false
                if case .bool(let stored)? = step.staticInputs[toolUsesLLMKey] {
                    usesLLM = stored
                }
                kind = .tool(
                    name: name, displayName: display, icon: icon, usesLLM: usesLLM
                )
            } else {
                guard let item = workflows.first(where: { $0.id == step.workflowId })
                else { return nil }
                kind = .workflow(item)
            }
            return StagedWorkflowStep(
                kind: kind,
                providerOverride: step.providerOverride,
                modelOverride: step.modelOverride
            )
        }
    }

    /// Engine per-step status → chip state. `skipped` maps to `pending` on
    /// purpose: the rail's language for "the chain stopped before me" has
    /// always been an un-run chip, and the engine's skip IS that fact.
    static func stepState(fromEngineStatus status: ChainStepStatus) -> StagedStepState {
        switch status {
        case .pending, .skipped: return .pending
        case .running: return .running
        case .completed: return .succeeded
        case .failed, .cancelled: return .failed
        }
    }

    /// True when the chain execution's top-level status has settled.
    static func isTerminal(_ status: String) -> Bool {
        status == "completed" || status == "failed" || status == "cancelled"
    }

    /// Identity of WHAT is staged — steps, order, pins — excluding the churn
    /// (chip states, thread ids) a run writes. Persist when THIS changes.
    static func structureKey(for staged: [StagedWorkflowStep]) -> String {
        staged
            .map { "\($0.stepKey):\($0.providerOverride ?? ""):\($0.modelOverride ?? "")" }
            .joined(separator: "|")
    }
}
