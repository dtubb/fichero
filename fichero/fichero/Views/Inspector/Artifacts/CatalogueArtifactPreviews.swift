import SwiftUI

enum CatalogueArtifactPreviews {
    static func items(from data: [String: AnyCodable]) -> [[String: Any]] {
        guard let rawItems = data["items"]?.value as? [Any] else { return [] }
        return rawItems.compactMap { item in
            if let dict = item as? [String: Any] {
                return dict
            }
            if let dict = item as? [String: AnyCodable] {
                return dict.mapValues(\.value)
            }
            return nil
        }
    }
}
