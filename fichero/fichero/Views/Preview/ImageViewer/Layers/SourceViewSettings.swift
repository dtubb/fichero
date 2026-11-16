import Foundation

/// The view settings a source remembers about itself (#6657): stored in the source's own metadata, so they
/// travel with it and survive any navigation. Selecting a source never writes them; only the person's own
/// toggle does. Show Image is the first (`preview-surface`, `layers.toggle.remembered-per-source`).
enum SourceViewSettings {
    static let showImageKey = "view.show_image"

    /// What the source stored, nil when the person never toggled it.
    static func showImage(in metadata: [String: AnyCodable]) -> Bool? {
        metadata[showImageKey]?.value as? Bool
    }

    /// What the preview starts at: the source's own choice, else the workspace's, else the default.
    static func startValue(stored: Bool?, workspace: Bool?, fallback: Bool) -> Bool {
        stored ?? workspace ?? fallback
    }

    /// The whole metadata to send with a toggle: the update replaces the dictionary, so every other key rides along.
    static func metadata(settingShowImage visible: Bool, in metadata: [String: AnyCodable]) -> [String: any Sendable] {
        var payload: [String: any Sendable] = metadata.mapValues { $0.value as any Sendable }
        payload[showImageKey] = visible
        return payload
    }
}
