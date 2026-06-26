import FicheroAPIClient
import Foundation

// MARK: - Raw metadata JSON editing

extension EntityDetailView {
    func saveMetadataJSON() async {
        isSavingMetadata = true
        defer { isSavingMetadata = false }
        guard LibraryManager.shared.globalLibrary != nil else {
            metadataSaveMessage = "No library"
            return
        }
        guard let entityId = entity.id else {
            metadataSaveMessage = "Entity ID missing"
            return
        }
        let trimmed = metadataJSON.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data),
              let dictAny = json as? [String: Any]
        else {
            metadataSaveMessage = "Invalid JSON object"
            return
        }
        guard let sendableMetadata = Self.makeSendableMetadata(dictAny) else {
            metadataSaveMessage = "Invalid JSON values"
            return
        }
        do {
            _ = try await entityService.patchEntity(entityId, metadata: sendableMetadata)
            metadataSaveMessage = "Saved"
        } catch {
            metadataSaveMessage = "Save failed"
        }
    }

    static func makeSendableMetadata(_ dict: [String: Any]) -> [String: any Sendable]? {
        var output: [String: any Sendable] = [:]
        for (key, value) in dict {
            guard let converted = makeSendableJSON(value) else { return nil }
            output[key] = converted
        }
        return output
    }

    // swiftlint:disable:next cyclomatic_complexity
    static func makeSendableJSON(_ value: Any) -> (any Sendable)? {
        switch value {
        case let string as String:
            return string
        case let int as Int:
            return int
        case let double as Double:
            return double
        case let bool as Bool:
            return bool
        case let number as NSNumber:
            return number.doubleValue
        case let array as [Any]:
            var converted: [any Sendable] = []
            converted.reserveCapacity(array.count)
            for item in array {
                guard let sendable = makeSendableJSON(item) else { return nil }
                converted.append(sendable)
            }
            return converted
        case let object as [String: Any]:
            return makeSendableMetadata(object)
        case _ as NSNull:
            return nil as String?
        default:
            return nil
        }
    }
}
