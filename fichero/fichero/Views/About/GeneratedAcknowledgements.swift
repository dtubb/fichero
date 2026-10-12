import Foundation

/// The acknowledgements the build generates from what the app actually bundles (#5639,
/// `about.acknowledgements.generated`): `scripts/write_acknowledgements.py` writes `acknowledgements.json` into the
/// embedded engine's `Contents/Resources` — every Python distribution in its `app_packages` and every Swift package
/// pin, each with its version, its licence and where its licence text is. The About window shows that list in place
/// of the curated one (`AboutAcknowledgements.entries`), keeping any curated entry the generated list lacks (the
/// platform frameworks, a runtime provisioned later). A build with no embedded engine (Debug, with an external one)
/// has no file: the curated list shows, and the window says so in one line.
enum GeneratedAcknowledgements {
    static let format = "fichero-acknowledgements-v1"
    static let fileName = "acknowledgements.json"

    /// What the window shows, and the one line it says about where the list came from (nil: the generated list).
    struct Loaded: Equatable {
        let entries: [Acknowledgement]
        let note: String?
    }

    struct File: Decodable {
        let format: String
        let components: [Component]
    }

    struct Component: Decodable, Equatable {
        let name: String
        let version: String
        let licence: String
        /// A path relative to `Contents/Resources/app_packages/`, or an https link; nil when there is none.
        let licenceText: String?
        /// "engine" or "app".
        let layer: String
        /// "python" or "swift".
        let kind: String

        enum CodingKeys: String, CodingKey {
            case name, version, licence, layer, kind
            case licenceText = "licence_text"
        }
    }

    enum ReadError: LocalizedError, Equatable {
        case wrongFormat(String)
        case unknownLayer(String)

        var errorDescription: String? {
            switch self {
            case .wrongFormat(let found): "it is \(found), not \(GeneratedAcknowledgements.format)"
            case .unknownLayer(let layer): "it names a layer this app does not know (\(layer))"
            }
        }
    }

    static let absentNote = "This build has no generated list (an external engine), so this is the built-in one."

    /// The list for this app: the generated one when its engine carries it, else the curated one, said so.
    @MainActor static func load(appBundle: URL = Bundle.main.bundleURL, curated: [Acknowledgement]) -> Loaded {
        guard let resources = engineResources(in: appBundle),
              let data = try? Data(contentsOf: resources.appendingPathComponent(fileName)) else {
            return Loaded(entries: curated, note: absentNote)
        }
        do {
            return Loaded(entries: merged(try parse(data, resources: resources), keeping: curated), note: nil)
        } catch {
            return Loaded(entries: curated, note: "The generated list could not be read (\(error.localizedDescription)), "
                          + "so this is the built-in one.")
        }
    }

    /// The embedded engine's `Contents/Resources`, wherever the build put the engine (Helpers or Resources).
    @MainActor static func engineResources(in appBundle: URL) -> URL? {
        #if os(macOS)
        for subpath in EmbeddedBackendService.engineBundleSubpaths {
            let resources = appBundle.appendingPathComponent(subpath).appendingPathComponent("Contents/Resources")
            if FileManager.default.fileExists(atPath: resources.appendingPathComponent(fileName).path) {
                return resources
            }
        }
        #endif
        // A touch device carries no engine of its own: it reads a Mac's.
        return nil
    }

    /// The generated components as rows: Python distributions under Engine, Swift pins under App; each linked to
    /// its licence text (a file in the bundle, or its link), else its project page.
    static func parse(_ data: Data, resources: URL) throws -> [Acknowledgement] {
        let file = try JSONDecoder().decode(File.self, from: data)
        guard file.format == format else { throw ReadError.wrongFormat(file.format) }
        return try file.components.map { component in
            let layer: AckLayer
            switch component.layer {
            case "engine": layer = .engine
            case "app": layer = .app
            default: throw ReadError.unknownLayer(component.layer)
            }
            let text = licenceTextURL(component.licenceText, resources: resources)
            return Acknowledgement(
                name: component.name, license: component.licence, url: projectURL(component, licenceText: text),
                layer: layer, version: component.version.isEmpty ? nil : component.version, licenceText: text
            )
        }
    }

    /// The licence text: an https link as it is, else a file under the engine's `app_packages`.
    static func licenceTextURL(_ pointer: String?, resources: URL) -> URL? {
        guard let pointer, !pointer.isEmpty else { return nil }
        if pointer.hasPrefix("https://") { return URL(string: pointer) }
        return resources.appendingPathComponent("app_packages").appendingPathComponent(pointer)
    }

    /// Where a component lives: a Swift pin's repository (its licence link without `/blob/…`), a Python
    /// distribution's PyPI page.
    static func projectURL(_ component: Component, licenceText: URL?) -> URL {
        if component.kind == "swift", let text = licenceText?.absoluteString, let blob = text.range(of: "/blob/") {
            return URL(string: String(text[..<blob.lowerBound])) ?? URL(string: "https://swiftpackageindex.com")!
        }
        let name = component.name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? component.name
        return URL(string: "https://pypi.org/project/\(name)/")!
    }

    /// The generated list, plus each curated entry it lacks (matched by distribution name), in the curated
    /// entry's own layer.
    static func merged(_ generated: [Acknowledgement], keeping curated: [Acknowledgement]) -> [Acknowledgement] {
        let have = Set(generated.map(\.versionKey))
        return generated + curated.filter { !have.contains($0.versionKey) }
    }
}
