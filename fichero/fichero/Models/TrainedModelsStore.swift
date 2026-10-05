import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// The models Fichero trained or fine-tuned, as the sidebar's Training node lists them
/// (`source.model.node-in-sidebar`, #5439), and each one's Inspector facts
/// (`source.model.node-inspector`). Ruled 2026-10-04: training is the sidebar node; a model
/// downloaded or imported has no training card, is not listed here and lives in Settings.
///
/// Everything is the engine's, read from each model's card through the generated client
/// (`GET /api/training/models`, `GET /api/training/model`); the app keeps nothing of its own.
/// The list is the engine's, not the project's: no card records the project it was trained in.
@MainActor
@Observable
final class TrainedModelsStore {
    /// Newest first, as the engine lists them.
    private(set) var models: [Components.Schemas.TrainedModelNode] = []
    /// One model's Inspector facts (its whole card and every evaluation), by model id. A load
    /// replaces only that model's entry.
    private(set) var inspected: [String: Components.Schemas.TrainedModelInspector] = [:]
    private(set) var errorMessage: String?
    /// Why one model's Inspector facts could not be read, by model id.
    private(set) var inspectErrors: [String: String] = [:]

    private let client: FicheroClient

    /// `models`/`inspected` seed a preview canvas; the app starts empty and loads.
    init(
        client: FicheroClient,
        models: [Components.Schemas.TrainedModelNode] = [],
        inspected: [String: Components.Schemas.TrainedModelInspector] = [:]
    ) {
        self.client = client
        self.models = models
        self.inspected = inspected
    }

    /// The Training node shows only when there is something in it (#5413's rule: a sidebar
    /// row appears only when non-empty).
    var showsTrainingNode: Bool { !models.isEmpty }

    /// Re-read the whole list: a resync of the engine's list, whose identity is the engine's
    /// set of training cards (there is no prior item to splice against).
    func loadModels() async {
        do {
            switch try await client.api.listTrainedModelsApiTrainingModelsGet() {
            case .ok(let success):
                models = try success.body.json.models
                errorMessage = nil
            case .undocumented(let code, _):
                errorMessage = "Could not read the trained models (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the trained models: \(error.localizedDescription)"
        }
    }

    /// Read one model's Inspector facts; replaces only that model's entry.
    func loadModel(_ modelId: String) async {
        do {
            switch try await client.api.trainedModelInspectorApiTrainingModelGet(query: .init(model: modelId)) {
            case .ok(let success):
                inspected[modelId] = try success.body.json
                inspectErrors[modelId] = nil
            case .unprocessableContent:
                inspectErrors[modelId] = "The engine did not accept this model id."
            case .undocumented(let code, _):
                inspectErrors[modelId] = code == 404
                    ? "Fichero has no training card for this model."
                    : "Could not read this model (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            inspectErrors[modelId] = "Could not read this model: \(error.localizedDescription)"
        }
    }
}

/// What the model Inspector says, worded from one model's card. Pure, so each sentence the
/// person reads is testable without a rendered view.
struct ModelNodeFacts {
    struct Score: Equatable {
        let policy: String
        let cer: String
    }

    static let notEvaluated = "Not evaluated yet"
    static let notForRelease = "This model was trained on material not for release"
    static let unknownLicence = "Unknown"

    let name: String
    let kind: String
    let summary: String?
    let base: String
    let teacher: String
    let trainingSet: [(label: String, value: String)]
    let trainedWhen: String
    let trainedWhere: String
    let job: String
    /// Nil before any evaluation: the Inspector says `notEvaluated`.
    let scores: [Score]?
    let scoresMeasured: String?
    let size: String
    let runsOn: [String]
    let licence: String
    let licenceNote: String?
    let mayPublish: Bool
    let publish: String

    init(_ model: Components.Schemas.TrainedModelInspector) {
        name = model.name
        kind = Self.kindName(model.kind)
        summary = model.summary
        base = model.base ?? "Unknown"
        teacher = model.teacher ?? "None"
        trainingSet = Self.setCounts(model.trainingSet?.additionalProperties)
        trainedWhen = Self.when(model.trainedAt)
        trainedWhere = Self.whereName(model.trainedWhere)
        job = model.jobId ?? "Unknown"
        scores = model.scores.map { scores in
            scores.cer.additionalProperties.keys.sorted().map { policy in
                Score(policy: policy, cer: Self.percent(scores.cer.additionalProperties[policy] ?? nil))
            }
        }
        scoresMeasured = model.scores.map { scores in
            let pages = scores.pages == 1 ? "1 held-out page" : "\(scores.pages) held-out pages"
            return "\(pages), \(Self.when(scores.measuredAt))"
        }
        size = model.sizeBytes.map { ByteCountFormatter.string(fromByteCount: Int64($0), countStyle: .file) }
            ?? "Unknown"
        runsOn = (model.runsOn ?? []).map { build in
            let place = build.runsOn ?? build.build
            return build.here ? "\(place) (here)" : "\(place) (not on this Mac)"
        }
        licence = model.licence ?? Self.unknownLicence
        licenceNote = model.licenceNote
        mayPublish = model.mayPublish
        publish = model.mayPublish ? "May be published" : (model.releaseNote ?? Self.notForRelease)
    }

    static func kindName(_ kind: String) -> String {
        switch kind {
        case "kraken-reader": return "Kraken reader"
        case "vision-lora": return "Vision model (fine-tuned)"
        default: return kind
        }
    }

    static func whereName(_ target: String?) -> String {
        switch target {
        case "huggingface-jobs": return "Hugging Face Jobs"
        case "this-mac": return "This Mac"
        case let other?: return other
        case nil: return "Unknown"
        }
    }

    static func when(_ iso: String?) -> String {
        guard let iso else { return "Unknown" }
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = withFraction.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        return date?.formatted(date: .abbreviated, time: .shortened) ?? iso
    }

    static func percent(_ cer: Double?) -> String {
        guard let cer else { return "Not measured" }
        return cer.formatted(.percent.precision(.fractionLength(1)))
    }

    private static let setLabels: [(key: String, label: String)] = [
        ("pages", "Pages"),
        ("lines", "Lines"),
        ("lines_read_by_a_model", "Lines read by a model"),
        ("lines_checked_by_a_person", "Lines checked by a person"),
        ("lines_left_out", "Lines left out"),
        ("held_out_pages", "Held-out pages")
    ]

    static func setCounts(_ set: OpenAPIRuntime.OpenAPIObjectContainer?) -> [(label: String, value: String)] {
        guard let set else { return [] }
        return setLabels.compactMap { entry in
            set.int(forKey: entry.key).map { (entry.label, "\($0)") }
        }
    }
}

/// Preview canvases' trained models, in the engine's own shape (recorded from
/// `training/model_nodes.py` over its test cards): a Kraken reader not yet evaluated and not for
/// release, and a vision student with held-out scores that may be published.
enum TrainedModelPreviewFixtures {
    static let readerId = "kraken-trained-0f4e2a6c1111"
    static let studentId = "fichero-trained/student"

    static let listJSON = """
    {"models": [
     {"id": "kraken-trained-0f4e2a6c1111", "name": "Notebook reader", "kind": "kraken-reader", "summary": null,
      "base": "kraken-mccatmus", "teacher": "google/gemini-3-flash-preview",
      "job_id": "0f4e2a6c-1111-2222-3333-444455556666", "trained_at": "2026-10-05T06:59:43.842138+00:00",
      "trained_where": "huggingface-jobs",
      "training_set": {"teacher": "google/gemini-3-flash-preview", "pages": 8, "lines": 210,
       "lines_read_by_a_model": 210, "lines_checked_by_a_person": 0, "lines_left_out": 3, "held_out_pages": 2},
      "scores": null, "evaluations": 0, "size_bytes": 15,
      "runs_on": [{"build": "kraken", "runs_on": "this Mac", "here": true}],
      "licence": null, "licence_note": null, "may_publish": false, "release_note": null},
     {"id": "fichero-trained/student", "name": "Qwen student", "kind": "vision-lora", "summary": null,
      "base": "Qwen/Qwen3-VL-4B-Instruct", "teacher": "google/gemini-3-flash-preview", "job_id": "job-v",
      "trained_at": "2026-10-04T10:00:00+00:00", "trained_where": "huggingface-jobs",
      "training_set": {"teacher": "google/gemini-3-flash-preview", "pages": 8, "lines": 210,
       "lines_read_by_a_model": 210, "lines_checked_by_a_person": 0, "lines_left_out": 3, "held_out_pages": 2},
      "scores": {"measured_at": "2026-10-05T01:00:00+00:00", "job_id": "eval-1", "checked": "anthropic/fable-checked",
       "pages": 2, "cer": {"diplomatic": 0.051000000000000004, "layout-insensitive": 0.031}},
      "evaluations": 1, "size_bytes": 2511,
      "runs_on": [{"build": "mlx", "runs_on": "Apple silicon", "here": true},
                  {"build": "hf", "runs_on": "Linux GPU (transformers, vLLM)", "here": false}],
      "licence": "apache-2.0", "licence_note": "Apache-2.0 on its Hub card.", "may_publish": true,
      "release_note": null}
    ]}
    """

    /// The Inspector shape for one listed model: the node plus its card and evaluation history.
    static func inspectorJSON(for modelId: String) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: Data(listJSON.utf8)) as? [String: Any],
              let models = object["models"] as? [[String: Any]],
              var model = models.first(where: { $0["id"] as? String == modelId }) else { return nil }
        model["card"] = ["display_name": model["name"] ?? "", "not_for_release": !(model["may_publish"] as? Bool ?? false)]
        model["evaluation_history"] = [[String: Any]]()
        guard let data = try? JSONSerialization.data(withJSONObject: model) else { return nil }
        return String(bytes: data, encoding: .utf8)
    }

    static var models: [Components.Schemas.TrainedModelNode] {
        (try? JSONDecoder().decode(Components.Schemas.TrainedModelNodes.self, from: Data(listJSON.utf8)))?.models ?? []
    }

    static func inspector(_ modelId: String) -> Components.Schemas.TrainedModelInspector? {
        inspectorJSON(for: modelId).flatMap {
            try? JSONDecoder().decode(Components.Schemas.TrainedModelInspector.self, from: Data($0.utf8))
        }
    }

    @MainActor
    static func store(client: FicheroClient) -> TrainedModelsStore {
        let inspected = [readerId, studentId].reduce(into: [String: Components.Schemas.TrainedModelInspector]()) {
            $0[$1] = inspector($1)
        }
        return TrainedModelsStore(client: client, models: models, inspected: inspected)
    }
}
