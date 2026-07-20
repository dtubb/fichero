import FicheroAPIClient
import Foundation
import OpenAPIRuntime

extension ActionLibraryService {
    // MARK: - Response Mapping Helpers

    /// Bridge a generated typed schema (e.g. `ActionResponse`) into the matching
    /// app model. The generated schemas encode to the same snake_case wire bytes
    /// the former `URLSession` decoders consumed, so this is a 1:1 mapping.
    /// `internal` so the `ActionsService` subclass can reuse it.
    func decodeModel<T: Decodable>(from value: some Encodable, as _: T.Type = T.self) throws -> T {
        let data = try JSONEncoder().encode(value)
        return try JSONDecoder().decode(T.self, from: data)
    }

    /// Bridge the free-form `items` container array returned by the list
    /// endpoints (`ActionListResponse.items`) into app models, mirroring the
    /// proven `IntegrationsService`/`NoteService` container-decode pattern.
    func decodeModels<T: Decodable>(from containers: [OpenAPIValueContainer], as _: T.Type = T.self) throws -> [T] {
        try containers.map { container in
            guard let object = container.value else { throw ActionLibraryError.serverError }
            let data = try JSONSerialization.data(withJSONObject: object)
            return try JSONDecoder().decode(T.self, from: data)
        }
    }

    /// Build an `OpenAPIObjectContainer` from a free-form `[String: Any]` node /
    /// graph dictionary for the from-node / composite request bodies.
    func objectContainer(from dict: [String: Any]) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        // #4024: `JSONSerialization.data(withJSONObject:)` raises an *Objective-C*
        // NSInvalidArgumentException (not a catchable Swift error) for non-JSON leaves such as
        // Date (__NSTaggedDate), which crashes the whole process. Validate first and surface a
        // catchable Swift error instead of letting the ObjC exception escape.
        guard JSONSerialization.isValidJSONObject(dict) else {
            throw ActionLibraryError.serverError
        }
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(OpenAPIRuntime.OpenAPIObjectContainer.self, from: data)
    }
}
