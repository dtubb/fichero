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
struct StagedWorkflowStep: Identifiable, Equatable {
    let id = UUID()
    let workflow: WorkflowSidebarItem
    var providerOverride: String?
    var modelOverride: String?

    var name: String { workflow.name }
    var folderPath: String { workflow.folderPath }

    /// What this step will actually run on, for the chip's tooltip. States the
    /// default explicitly rather than leaving a blank that could mean either
    /// "unset" or "inherited".
    var modelDescription: String {
        guard let model = modelOverride, !model.isEmpty else {
            return "default model for this workflow"
        }
        return model.split(separator: "/").last.map(String.init) ?? model
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
