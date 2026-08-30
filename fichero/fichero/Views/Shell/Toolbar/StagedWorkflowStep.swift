import Foundation

/// One step of a chain assembled in the capability bar.
///
/// Carries its OWN provider and model (Daniel, 2026-08-28: "so you can quickly
/// do Opus transcribe, and then Apple Intelligence for entities"). A chain with
/// a single model for every step forces the most expensive choice onto the
/// cheapest work — reading a hard hand deserves Opus, counting entities in the
/// text it produced does not.
///
/// `nil` means the step runs on whatever the workflow resolves by itself,
/// which is the alias the model chip reports. A step is identified by its own
/// UUID, not by the workflow id, because the same verb can appear twice in a
/// chain with different models — transcribe with Opus, then transcribe again
/// with a cheaper model to compare.
/// Where a step is in its lifecycle. Colour follows this, so a chain that has
/// half finished reads as half finished rather than uniformly blue (Daniel,
/// 2026-08-28: "when it runs and the steps work, they should change colour").
enum StagedStepState: Equatable {
    case pending
    case running
    case succeeded
    case failed
}

/// What a chain step runs: a saved workflow, or a single tool.
///
/// Tools are the third level of Daniel's taxonomy (tools, workflows, chains)
/// and the one the bar could not reach. The engine executes STORED workflows
/// only, so a tool step is realised as a one-step workflow — created when the
/// chain is RUN, never while merely browsing, because writing into the user's
/// library as a side effect of opening a popover is not browsing.
enum StagedStepKind: Equatable {
    case workflow(WorkflowSidebarItem)
    case tool(name: String, displayName: String, icon: String, usesLLM: Bool)
}

struct StagedWorkflowStep: Identifiable, Equatable {
    let id = UUID()
    let kind: StagedStepKind
    var providerOverride: String?
    var modelOverride: String?
    var state: StagedStepState = .pending
    /// Thread id of the run this step produced, so double-clicking a
    /// finished chip can open what it made.
    var threadId: String?

    /// The saved workflow this step runs, when it has one. A tool step has
    /// none until the run materialises it.
    var workflow: WorkflowSidebarItem? {
        if case .workflow(let value) = kind { return value }
        return nil
    }

    var name: String {
        switch kind {
        case .workflow(let value): return value.name
        case .tool(_, let displayName, _, _): return displayName
        }
    }

    var displayName: String {
        switch kind {
        case .workflow(let value): return value.displayName
        case .tool(_, let displayName, _, _): return displayName
        }
    }

    var folderPath: String {
        switch kind {
        case .workflow(let value): return value.folderPath
        case .tool: return "/Tools"
        }
    }

    /// A tool step's glyph comes from the engine's registry entry rather than
    /// the folder map, since it belongs to no workflow folder.
    var toolIcon: String? {
        if case .tool(_, _, let icon, _) = kind { return icon }
        return nil
    }

    /// Stable identity of WHAT this step runs, for cache keys.
    var stepKey: String {
        switch kind {
        case .workflow(let value): return value.id
        case .tool(let name, _, _, _): return "tool:\(name)"
        }
    }

    var isTool: Bool {
        if case .tool = kind { return true }
        return false
    }

    /// What this step will actually run on, for the chip's tooltip. States the
    /// default explicitly rather than leaving a blank that could mean either
    /// "unset" or "inherited".
    var modelDescription: String {
        guard let model = modelOverride, !model.isEmpty else {
            return "default model for this workflow"
        }
        // One shortening rule for the whole feature — the chip, this label
        // and the pin menu must agree on how a model reads (review,
        // 2026-08-29).
        return ModelChipToolbarItem.shorten(model)
    }

    /// True when the user pinned a model to this step rather than inheriting.
    var hasModelOverride: Bool {
        !(modelOverride ?? "").isEmpty
    }
}

/// A provider/model pair a chain step can be pinned to, as configured in
/// Settings → AI Defaults. Kept as a flat list rather than a tier alias so the
/// chip can state the concrete model it will call, which is the fact the
/// `$vision_small` failure showed was missing.
struct WorkflowBarModelChoice: Equatable {
    let label: String
    let provider: String
    let model: String
}
