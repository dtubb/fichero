import Foundation
@testable import Fichero
import Testing

/// #5639: the About window credits what the build bundles, read from the `acknowledgements.json` the build writes into
/// the embedded engine's Resources, grouped by layer, each with its version and licence and its licence text; the
/// curated list stays for what the file lacks, and shows alone, said so, when a build has no file. What breaks without
/// these: a licence text pointing nowhere, a Swift pin linked to its licence file instead of its project, a file of
/// another format read as if it were this one, or a Debug build showing an empty list.
@MainActor
@Suite("The generated acknowledgements (#5639)", .serialized)
struct GeneratedAcknowledgementsTests {
    private static let resources = URL(fileURLWithPath: "/Applications/Fichero.app/Contents/Resources/Fichero Server.app/Contents/Resources")

    private static let json = """
    {"format": "fichero-acknowledgements-v1", "components": [
     {"name": "duckdb", "version": "1.5.1", "licence": "MIT", "licence_text": "duckdb-1.5.1.dist-info/LICENSE",
      "layer": "engine", "kind": "python"},
     {"name": "fastapi", "version": "0.118.0", "licence": "MIT", "licence_text": null, "layer": "engine", "kind": "python"},
     {"name": "sparkle", "version": "2.7.1", "licence": "MIT",
      "licence_text": "https://github.com/sparkle-project/Sparkle/blob/0ef1ee02/LICENSE", "layer": "app", "kind": "swift"}]}
    """

    @Test("each component becomes a row in its layer, with its version, licence and licence text")
    func parse() throws {
        let rows = try GeneratedAcknowledgements.parse(Data(Self.json.utf8), resources: Self.resources)
        #expect(rows.map(\.name) == ["duckdb", "fastapi", "sparkle"])
        #expect(rows.map(\.layer) == [.engine, .engine, .app])
        #expect(rows[0].version == "1.5.1" && rows[0].license == "MIT")
        #expect(rows[0].licenceText == Self.resources.appendingPathComponent("app_packages/duckdb-1.5.1.dist-info/LICENSE"))
        #expect(rows[1].licenceText == nil)
        #expect(rows[1].url == URL(string: "https://pypi.org/project/fastapi/"))
        #expect(rows[2].licenceText == URL(string: "https://github.com/sparkle-project/Sparkle/blob/0ef1ee02/LICENSE"))
        #expect(rows[2].url == URL(string: "https://github.com/sparkle-project/Sparkle"), "a pin links to its repository")
    }

    @Test("a click opens a web page: the licence link, else the project page, never a file inside the bundle (#6011)")
    func destination() throws {
        let rows = try GeneratedAcknowledgements.parse(Data(Self.json.utf8), resources: Self.resources)
        #expect(rows[0].destination == URL(string: "https://pypi.org/project/duckdb/"), "a bundled licence file falls back to the project page")
        #expect(rows[1].destination == rows[1].url)
        #expect(rows[2].destination == rows[2].licenceText, "a licence link is opened as it is")
        #expect(rows.allSatisfy { !$0.destination.isFileURL })
    }

    @Test("a file of another format, or a layer this app does not know, is refused, never read as this one")
    func refusals() {
        let other = #"{"format": "fichero-acknowledgements-v2", "components": []}"#
        #expect(throws: GeneratedAcknowledgements.ReadError.wrongFormat("fichero-acknowledgements-v2")) {
            _ = try GeneratedAcknowledgements.parse(Data(other.utf8), resources: Self.resources)
        }
        let layer = """
        {"format": "fichero-acknowledgements-v1", "components": [
         {"name": "x", "version": "1", "licence": "MIT", "licence_text": null, "layer": "cloud", "kind": "python"}]}
        """
        #expect(throws: GeneratedAcknowledgements.ReadError.unknownLayer("cloud")) {
            _ = try GeneratedAcknowledgements.parse(Data(layer.utf8), resources: Self.resources)
        }
    }

    @Test("the curated entries the generated list lacks are kept, in their own layer; the rest are replaced")
    func merge() throws {
        let generated = try GeneratedAcknowledgements.parse(Data(Self.json.utf8), resources: Self.resources)
        let curated = [
            Acknowledgement(name: "DuckDB", license: "MIT License", url: URL(string: "https://duckdb.org")!, layer: .engine),
            Acknowledgement(name: "SwiftUI & AppKit", license: "Apple platform frameworks",
                            url: URL(string: "https://developer.apple.com")!, layer: .app),
        ]
        let merged = GeneratedAcknowledgements.merged(generated, keeping: curated)
        #expect(merged.map(\.name) == ["duckdb", "fastapi", "sparkle", "SwiftUI & AppKit"])
        #expect(Set(merged.map(\.id)).count == merged.count, "rows stay uniquely identified")
    }

    @Test("a row shows the engine's live version first, else the bundled one, else the licence alone")
    func detailLine() {
        let bundled = Acknowledgement(name: "duckdb", license: "MIT", url: URL(string: "https://duckdb.org")!,
                                      layer: .engine, version: "1.5.1")
        #expect(AcknowledgementsView.detailLine(for: bundled, versions: [:]) == "v1.5.1 · MIT")
        #expect(AcknowledgementsView.detailLine(for: bundled, versions: ["duckdb": "1.5.2"]) == "v1.5.2 · MIT")
        let curated = Acknowledgement(name: "Whisper", license: "MIT License", url: URL(string: "https://openai.com")!,
                                      layer: .onDevice)
        #expect(AcknowledgementsView.detailLine(for: curated, versions: [:]) == "MIT License")
    }

    @Test("an app whose engine carries the file shows it; one without shows the curated list and says so")
    func loadFromABundle() throws {
        let app = FileManager.default.temporaryDirectory.appendingPathComponent("GeneratedAcks-\(UUID().uuidString).app")
        defer { try? FileManager.default.removeItem(at: app) }
        let curated = AboutAcknowledgements.entries

        let absent = GeneratedAcknowledgements.load(appBundle: app, curated: curated)
        #expect(absent.entries == curated)
        #expect(absent.note == GeneratedAcknowledgements.absentNote)

        let engineResources = app.appendingPathComponent("Contents/Resources/Fichero Server.app/Contents/Resources")
        try FileManager.default.createDirectory(at: engineResources, withIntermediateDirectories: true)
        try Data(Self.json.utf8).write(to: engineResources.appendingPathComponent(GeneratedAcknowledgements.fileName))
        let present = GeneratedAcknowledgements.load(appBundle: app, curated: curated)
        #expect(present.note == nil)
        #expect(present.entries.prefix(3).map(\.name) == ["duckdb", "fastapi", "sparkle"])

        try Data("not json".utf8).write(to: engineResources.appendingPathComponent(GeneratedAcknowledgements.fileName))
        let unreadable = GeneratedAcknowledgements.load(appBundle: app, curated: curated)
        #expect(unreadable.entries == curated)
        #expect(unreadable.note?.hasPrefix("The generated list could not be read") == true, "said, never silent")
    }
}
