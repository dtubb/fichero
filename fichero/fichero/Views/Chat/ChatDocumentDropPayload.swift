import Foundation
import UniformTypeIdentifiers

enum ChatDocumentDropPayload {
    static let typeIdentifiers = [
        UTType.text.identifier,
        UTType.plainText.identifier
    ]

    static func firstSupportedTypeIdentifier(in provider: NSItemProvider) -> String? {
        typeIdentifiers.first { provider.hasItemConformingToTypeIdentifier($0) }
    }

    static func documentID(from item: NSSecureCoding?) -> String? {
        if let data = item as? Data,
           let string = String(data: data, encoding: .utf8) {
            return documentID(from: string)
        }

        if let data = item as? NSData,
           let string = String(data: data as Data, encoding: .utf8) {
            return documentID(from: string)
        }

        if let string = item as? String {
            return documentID(from: string)
        }

        if let string = item as? NSString {
            return documentID(from: string as String)
        }

        return nil
    }

    static func documentID(from payload: String) -> String? {
        let trimmed = payload.trimmingCharacters(in: .whitespacesAndNewlines)
        let candidate: String

        if trimmed.hasPrefix("doc:") {
            candidate = String(trimmed.dropFirst(4))
        } else if trimmed.contains(":") {
            return nil
        } else {
            candidate = trimmed
        }

        guard !candidate.isEmpty, UUID(uuidString: candidate) != nil else {
            return nil
        }

        return candidate
    }
}
