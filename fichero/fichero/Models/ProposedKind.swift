import Foundation

/// A kind a run proposed for a node, waiting for a person (#5600,
/// `source.extract.kinds-proposed-as-prototypes`): the engine keeps it on the node, under
/// `metadata.proposed_attributes.prototype` of `GET /api/documents/{id}`. The app reads it as the
/// engine wrote it and answers it through the engine (Accept / Reject); it never decides a kind.
struct ProposedKind: Equatable, Sendable {
    /// The prototype key the node gets when it is accepted.
    let key: String
    /// What the model named the kind.
    let label: String
    /// What the model said, as the run recorded it; nil when the run kept nothing.
    let said: String?
    /// The tool that proposed it ("classify").
    let tool: String?
    /// The model that answered.
    let model: String?
    /// The run that proposed it.
    let runId: String?

    /// The proposal waiting on this node's metadata, or nil when none waits (none made, or answered).
    init?(metadata: [String: AnyCodable]) {
        guard let proposed = metadata["proposed_attributes"]?.value as? [String: Any],
              let prototype = proposed["prototype"] as? [String: Any],
              prototype["state"] as? String == "proposed",
              let key = prototype["value"] as? String, !key.isEmpty else { return nil }
        let source = prototype["source"] as? [String: Any] ?? [:]
        self.key = key
        self.label = (prototype["label"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? key
        self.said = (source["said"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        self.tool = source["tool"] as? String
        self.model = source["model"] as? String
        self.runId = source["run_id"] as? String
    }

    /// "Proposed by classify (qwen) in run 1a2b3c4d", from what the run recorded.
    var byWhom: String {
        var line = "Proposed by \(tool ?? "a run")"
        if let model, !model.isEmpty { line += " (\(model))" }
        if let runId, !runId.isEmpty { line += " in run \(runId.prefix(8))" }
        return line
    }
}
