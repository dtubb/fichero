import FicheroAPIClient
import Foundation

extension WorkflowNode {
    /// This node's config in the shape `POST /workflows/tools/{name}/prompt`
    /// wants. One conversion, shared by the node editor's prompt preview and
    /// the capability bar, so the two can never disagree about what a step
    /// would send.
    var promptConfigDict: [String: any Sendable] {
        guard let config else { return [:] }
        var result: [String: any Sendable] = [:]
        for (key, value) in config {
            if let converted = value.sendableValue {
                result[key] = converted
            }
        }
        return result
    }
}

extension AnyCodableValue {
    /// The value as the plain Sendable the prompt endpoint's JSON body wants.
    ///
    /// Recursive on purpose: the old conversion handled only the four scalar
    /// cases, so a classify node whose `categories` array a user had edited
    /// PREVIEWED the default-categories prompt while the run used the edited
    /// ones — the preview's one job, failed silently (review, 2026-08-29).
    /// `.null` maps to nil and is omitted, which JSON-wise means the same.
    var sendableValue: (any Sendable)? {
        switch self {
        case .string(let value): return value
        case .int(let value): return value
        case .double(let value): return value
        case .bool(let value): return value
        case .array(let values): return values.compactMap(\.sendableValue)
        case .dictionary(let entries):
            var result: [String: any Sendable] = [:]
            for (key, entry) in entries {
                if let converted = entry.sendableValue { result[key] = converted }
            }
            return result
        case .null: return nil
        }
    }
}

/// One step of a workflow, as it reads to someone deciding whether to run it.
///
/// The bar's verbs are workflow NAMES, which say what the thing is called and
/// nothing about what it will do, what it reads, or what it asks a model.
/// Daniel, 2026-08-28: "make it easy to see the prompts used in tools, and the
/// steps in the workflows, as well as the input."
struct WorkflowStepPreview: Identifiable, Hashable, Sendable {
    let id: String
    let index: Int
    /// The node's own label, which the author may have renamed.
    let label: String
    let toolName: String
    let icon: String
    /// Pinned on the node; empty when the step follows the run's model.
    let model: String
    /// What this step reads, named as the graph names it.
    let inputSummary: String
    /// The prompt this step would send with its CURRENT config — resolved by
    /// the engine's own builder, not the frozen `default_prompt`, so a Table
    /// node set to CSV shows the CSV prompt.
    var prompt: String?
    /// False for a step that sends no prompt (a source, a save, a join).
    let usesModel: Bool
}

extension WorkflowStore {
    /// Steps for a workflow, or nil when they have not been fetched yet.
    func steps(for workflowId: String) -> [WorkflowStepPreview]? {
        workflowStepCache[workflowId]
    }

    /// Loads and caches a workflow's steps and each step's resolved prompt.
    ///
    /// The sidebar list is the `summary: true` payload — labels and a node
    /// count, no graph — because pulling 50 presets' graphs through AnyCodable
    /// was the folder-open spin. So a popover that wants the steps asks for
    /// that ONE workflow, here in the store (the only endpoint accessor), and
    /// the answer is kept: a preset's graph does not change while a popover is
    /// open. Idempotent — reopening the popover costs nothing.
    func loadSteps(for workflowId: String) async {
        if workflowStepCache[workflowId] != nil { return }
        if workflowStepsLoading.contains(workflowId) { return }
        workflowStepsLoading.insert(workflowId)
        defer { workflowStepsLoading.remove(workflowId) }

        do {
            let definition = try await workflowService.getWorkflow(workflowId)
            var previews: [WorkflowStepPreview] = definition.nodes.enumerated().map { index, node in
                let info = toolRegistry[node.tool.lowercased()]
                let label = node.label.flatMap { $0.isEmpty ? nil : $0 }
                return WorkflowStepPreview(
                    id: node.id,
                    index: index,
                    label: label ?? info?.displayName ?? node.tool,
                    toolName: node.tool,
                    icon: info?.icon ?? "gearshape",
                    model: node.modelName ?? "",
                    inputSummary: Self.inputSummary(for: node, in: definition),
                    prompt: nil,
                    usesModel: node.usesLLM
                )
            }

            // Resolve each prompting step's ACTUAL prompt through the engine's
            // builder — the same call the node editor's prompt preview makes,
            // so the bar and the editor can never show different prompts for
            // the same node. A step the engine will not resolve falls back to
            // the registered default, labelled by the UI as such.
            for (offset, step) in previews.enumerated() where step.usesModel {
                guard let node = definition.nodes.first(where: { $0.id == step.id })
                else { continue }
                let resolved = try? await workflowService.getToolPrompt(
                    toolName: step.toolName,
                    config: node.promptConfigDict
                )
                // `try?` swallows CancellationError too — closing the popover
                // mid-fetch used to fall through to the DEFAULT prompt and
                // CACHE it as this node's answer, permanently wrong until the
                // next workflow edit (review, 2026-08-29). A cancelled load
                // caches nothing.
                if Task.isCancelled { return }
                previews[offset].prompt = resolved
                    ?? toolRegistry[step.toolName.lowercased()]?.defaultPrompt
            }
            workflowStepCache[workflowId] = previews
        } catch {
            if error.isCancellationError { return }
            logger.error(
                "Failed to load steps for \(workflowId): \(String(describing: error))"
            )
        }
    }

    /// Which ports actually feed this node. "documents, files" for a step that
    /// reads the page, "text" for one that reads what the step before it
    /// wrote — the distinction someone is trying to see when they ask what a
    /// step runs on.
    private static func inputSummary(
        for node: WorkflowNode,
        in definition: WorkflowDefinition
    ) -> String {
        let fed = definition.edges
            .filter { $0.targetNodeId == node.id }
            .map(\.targetPortId)
        if fed.isEmpty {
            return node.tool == "files" ? "the selection" : "no input"
        }
        return Set(fed).sorted().joined(separator: ", ")
    }
}
