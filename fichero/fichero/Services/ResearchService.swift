import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

@MainActor
@Observable
final class ResearchService {
    let client: FicheroClient
    let logger = Logger(subsystem: "app.fichero.fichero", category: "ResearchService")

    var projects: [ResearchProject] = []
    var selectedProjectId: String?
    var isLoading = false
    var error: String?

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    enum ServiceError: Error, LocalizedError {
        case unexpectedResponse

        // Shown to users via researchService.error; conform to LocalizedError so
        // it's not the generic "operation couldn't be completed" message (#2500).
        var errorDescription: String? {
            "Unexpected response from the research service."
        }
    }

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }

            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }

            let dateFormatter = DateFormatter()
            dateFormatter.locale = Locale(identifier: "en_US_POSIX")
            dateFormatter.timeZone = TimeZone(identifier: "UTC")
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date: \(dateString)"
            )
        }
        return decoder
    }()

    static let encoder = JSONEncoder()

    func decodeModel<T: Decodable>(from value: some Encodable, as _: T.Type = T.self) throws -> T {
        let data = try Self.encoder.encode(value)
        return try Self.decoder.decode(T.self, from: data)
    }

    func decodeModels<T: Decodable>(
        from containers: [OpenAPIValueContainer],
        as _: T.Type = T.self
    ) throws -> [T] {
        try containers.map { container in
            guard let object = container.value else { throw ServiceError.unexpectedResponse }
            let data = try JSONSerialization.data(withJSONObject: object)
            return try Self.decoder.decode(T.self, from: data)
        }
    }

    func projectStatus(_ status: ResearchProjectStatus?) -> Components.Schemas.FicheroServerModelsResearchProjectStatus? {
        status.flatMap { .init(rawValue: $0.rawValue) }
    }

    func planStatus(_ status: ResearchPlanStatus?) -> Components.Schemas.PlanStatus? {
        status.flatMap { .init(rawValue: $0.rawValue) }
    }

    func taskStatus(_ status: ResearchTaskStatus?) -> Components.Schemas.TaskStatus? {
        status.flatMap { .init(rawValue: $0.rawValueForAPI) }
    }

    func stepStatus(_ status: ResearchStepStatus?) -> Components.Schemas.StepStatus? {
        status.flatMap { .init(rawValue: $0.rawValue) }
    }

    func stepTool(_ tool: ResearchStepTool) -> Components.Schemas.StepTool {
        Components.Schemas.StepTool(rawValue: tool.rawValue) ?? .webSearch
    }

    func researchNoteType(_ noteType: String?) -> Components.Schemas.ResearchNoteType? {
        noteType.flatMap { .init(rawValue: $0) }
    }

    func researchSourceType(_ sourceType: String) -> Components.Schemas.SearchSourceType {
        Components.Schemas.SearchSourceType(rawValue: sourceType) ?? .url
    }
}
