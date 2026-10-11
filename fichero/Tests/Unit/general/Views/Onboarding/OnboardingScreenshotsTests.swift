//
//  OnboardingScreenshotsTests.swift
//  FicheroTests
//
//  Every onboarding screen as a PNG at 2x, for the maintainer to mark up (#5660, 2026-10-11). Runs ONLY when
//  FICHERO_SCREENSHOTS_DIR names a folder (with xcodebuild: TEST_RUNNER_FICHERO_SCREENSHOTS_DIR=<folder>); the
//  files are numbered in the order a person meets the screens.
//
//  The real views, with real stores, reading a fixture engine: every request the project's client makes is
//  answered from `test-fixtures/files/onboarding/`, which is the engine's own answers for a Spanish colonial
//  manuscript box of 92 pages (purposes, jobs, the assembled recipe, the Start plan, the finder's candidates),
//  captured from the engine and then set to what the maintainer saw on 2026-10-10: Find regions held back for
//  its licence, and the reading model (Qwen2.5-VL 7B) already downloading.
//
//  Drawn through NSHostingView's cacheDisplay at twice the point size, not ImageRenderer: ImageRenderer draws
//  AppKit-backed controls (List, ScrollView, text fields, pickers) as empty placeholders, and setup is made of them.
//

#if os(macOS)
import AppKit
@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

/// The fixture engine: each route setup reads, answered from the onboarding fixture files.
private final class OnboardingFixtureEngine: URLProtocol {
    nonisolated(unsafe) static var served: [String] = []
    /// Requests no fixture answered: the test fails on any, since its reply would show on a screen.
    nonisolated(unsafe) static var unanswered: [String] = []
    /// The fixture files by name, read on the main actor before any request (`loadFixtures()`).
    nonisolated(unsafe) static var files: [String: Data] = [:]

    static let names = ["purposes", "jobs", "project", "plan", "assembled", "candidates-read-a-line",
                        "candidates-find-regions", "languages", "scripts", "derived", "topics", "bakeoffs",
                        "kept-exports", "candidates-find-names-tag-words"]

    static func loadFixtures() throws {
        for name in names {
            files[name] = try Data(contentsOf: TestFixtures.sampleFile("onboarding/\(name).json"))
        }
    }

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    /// Each route's fixture file, as `<method> <path>`. Saving the setup (PUT) answers the setup saved, as the
    /// engine does; the candidates are by the step's job (`fixture(for:)`).
    nonisolated static let routes: [String: String] = [
        "GET /api/recipes/purposes": "purposes",
        "GET /api/recipes/jobs": "jobs",
        "GET /api/recipes/project": "project",
        "PUT /api/recipes/project": "project",
        "GET /api/recipes/project/start": "plan",
        "POST /api/recipes/assemble": "assembled",
        "GET /api/recipes/languages": "languages",
        "GET /api/recipes/scripts": "scripts",
        "GET /api/recipes/derived": "derived",
        "GET /api/topics": "topics",
        "GET /api/recipes/project/bakeoffs": "bakeoffs",
        "GET /api/export/kept": "kept-exports"
    ]

    /// The fixture file for a request, or nil (answered 404, as an engine without that route would).
    nonisolated static func fixture(for request: URLRequest) -> String? {
        let path = request.url?.path ?? ""
        if path == "/api/recipes/candidates" {
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
            return "candidates-\(query.first { $0.name == "job" }?.value ?? "read-a-line")"
        }
        return routes["\(request.httpMethod ?? "GET") \(path)"]
    }

    override func startLoading() {
        let name = Self.fixture(for: request)
        let data = name.flatMap { Self.files[$0] }
        let asked = "\(request.httpMethod ?? "") \(request.url?.path ?? "")"
        Self.served.append("\(asked) -> \(name ?? "404")")
        if data == nil { Self.unanswered.append(asked) }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: data == nil ? 404 : 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data ?? Data(#"{"detail":"not in the onboarding fixture"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

enum OnboardingScreenshots {
    /// Where the PNGs go; nil leaves the suite disabled.
    nonisolated static var directory: URL? {
        ProcessInfo.processInfo.environment["FICHERO_SCREENSHOTS_DIR"].flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0) }
    }
}

@MainActor
@Suite(.serialized, .enabled(if: OnboardingScreenshots.directory != nil, "set FICHERO_SCREENSHOTS_DIR to write them"))
struct OnboardingScreenshotsTests {
    /// The box from the maintainer's test of 2026-10-10, as a project whose every request the fixture engine answers.
    private static func project() -> LibraryManager.LibraryReference {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OnboardingFixtureEngine.self]
        return LibraryManager.LibraryReference(
            url: FileManager.default.temporaryDirectory.appendingPathComponent("Escribania 1023.fichero"),
            document: FicheroDocument(),
            displayName: "Escribanía 1023 · Popayán, 1650–1700",
            session: URLSession(configuration: configuration)
        )
    }

    /// The window's environment, as `LibraryPreviewFixtures.environment` gives a preview, for this project.
    private static func inWindow<V: View>(_ view: V, project: LibraryManager.LibraryReference) -> some View {
        view
            .libraryServiceEnvironment(project)
            .environment(AppState())
            .environment(LibraryManager.shared)
            .environment(WindowState(libraryId: project.id))
            .environment(WorkflowExecutionObserver())
            .environment(KGFocusState())
    }

    /// Host `view` at `size` points, let its tasks read the fixture engine, and write it at 2x as `name`.
    private static func write<V: View>(_ view: V, size: CGSize, name: String, to folder: URL) async throws -> URL {
        let hosting = NSHostingView(rootView: view)
        hosting.frame = CGRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: hosting.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: .aqua)
        window.contentView = hosting
        defer { window.close() }
        // The views' own .task reads run now, against the fixture engine.
        try await Task.sleep(for: .milliseconds(1500))
        hosting.layoutSubtreeIfNeeded()
        flattenVisualEffects(in: hosting)
        hosting.display()
        let rep = try #require(NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(size.width * 2), pixelsHigh: Int(size.height * 2),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
        ))
        rep.size = size
        hosting.cacheDisplay(in: hosting.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        let url = folder.appendingPathComponent(name)
        try png.write(to: url)
        return url
    }

    /// A sidebar's selected row is drawn by its table as a material (a visual-effect layer), which an offscreen
    /// cacheDisplay paints solid black; round 2's "inactive" material was still black. So the tables draw no
    /// highlight of their own here, and each selected row gets a plain rounded fill in the system's selection
    /// colour behind its content, which cacheDisplay draws as the window shows it.
    private static func flattenVisualEffects(in view: NSView) {
        if let table = view as? NSTableView {
            table.selectionHighlightStyle = .none
        }
        if let effect = view as? NSVisualEffectView, effect.superview is NSTableRowView {
            effect.isHidden = true
        }
        if let row = view as? NSTableRowView, row.isSelected,
           !row.subviews.contains(where: { $0.identifier == selectionFill }) {
            let fill = NSBox(frame: row.bounds.insetBy(dx: 10, dy: 1))
            fill.identifier = selectionFill
            fill.boxType = .custom
            fill.borderWidth = 0
            fill.cornerRadius = 6
            fill.fillColor = NSColor.unemphasizedSelectedContentBackgroundColor
            fill.autoresizingMask = [.width, .height]
            row.addSubview(fill, positioned: .below, relativeTo: nil)
        }
        view.subviews.forEach(flattenVisualEffects(in:))
    }

    private static let selectionFill = NSUserInterfaceItemIdentifier("screenshot-selection-fill")

    @Test("every onboarding screen, in flow order, as a PNG at 2x")
    func writeEveryOnboardingScreen() async throws {
        let folder = try #require(OnboardingScreenshots.directory)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let project = Self.project()
        try OnboardingFixtureEngine.loadFixtures()
        OnboardingFixtureEngine.unanswered = []
        let setup = project.recipeSetupStore
        // What setup reads when it opens on this project, read first so every screen draws it at once.
        await setup.loadSaved()
        await setup.loadPurposes()
        await setup.loadJobs()
        await setup.loadStartPlan()
        let named = NewProjectStore(libraryManager: LibraryManager.shared)
        named.name = "Escribanía 1023 · Popayán, 1650–1700"

        let window = CGSize(width: 820, height: 600)
        let sheet = CGSize(width: 640, height: 560)
        var written: [URL] = []
        func shot<V: View>(_ name: String, _ size: CGSize, _ view: V) async throws {
            written.append(try await Self.write(Self.inWindow(view, project: project), size: size, name: name, to: folder))
        }

        try await shot("01-welcome.png", window, FirstRunWindow(mode: .firstRun))
        try await shot("02-your-project.png", window,
                       FirstRunWindow(mode: .firstRun, initialStep: .project, newProject: named))
        try await shot("03-your-material.png", window, FirstRunWindow(mode: .setUp, project: project, initialStep: .material))
        // Your material is longer than its card: all of it, as the card scrolls through it (languages, scripts,
        // what the material is).
        try await shot("04-your-material-whole.png", CGSize(width: 620, height: 620), VStack(alignment: .leading, spacing: 16) {
            RecipeMaterialSourceFields(store: setup, importer: project.importService, syncFolders: project.syncFolderStore)
            Divider()
            RecipeAboutFields(store: setup)
            Spacer(minLength: 0)
        }.padding(22))
        try await shot("05-what-you-want-to-do.png", window,
                       FirstRunWindow(mode: .setUp, project: project, initialStep: .purpose))
        try await shot("06-ready.png", window, FirstRunWindow(mode: .setUp, project: project, initialStep: .ready))
        // Ready is longer than its card: the whole plan, top to bottom, as the card scrolls through it.
        try await shot("07-ready-whole-plan.png", CGSize(width: 620, height: 3200), VStack {
            RecipeReadyFields(store: setup, onFix: { _ in }, keptExports: project.keptExportStore, project: project)
            Spacer(minLength: 0)
        }.padding(22))
        try await shot("08-find-a-reader.png", sheet,
                       ModelFinderSheet(project: project, setup: setup,
                                        step: .init(id: "read-a-line", job: "read-a-line"), onDone: {}))
        // Choose a model… on Find names (#5660 item 4): spaCy in use, MLX models to download, Apple Intelligence
        // and Claude saying why Fichero cannot run them yet.
        try await shot("09-who-finds-names.png", CGSize(width: 640, height: 900),
                       ModelFinderSheet(project: project, setup: setup,
                                        step: .init(id: "find-names-tag-words", job: "find-names-tag-words"), onDone: {}))
        try await shot("10-review-the-licence.png", sheet,
                       LicenceReviewSheet(finder: project.modelFinderStore, setup: setup,
                                          step: .init(id: "find-regions", job: "find-regions"), onDone: {}))
        try await shot("11-run-strip-after-start.png", CGSize(width: 1100, height: 44), ProjectRunStripRow(
            strip: ProjectRunStrip(
                jobId: "recipe-run", isLive: true, title: "Find lines · stage 1 of 5",
                detail: "12 done · 0 failed · 80 left · 9 min left · "
                    + "Waiting for Qwen2.5-VL 7B (OCR) to download for step correct"),
            failure: nil, onReadAgain: { _ in }, onShowDetails: {}, onClose: {}
        ).padding(.horizontal, 12).frame(maxHeight: .infinity))

        #expect(written.count == 11)
        // No screen may show the fixture's own words: every request is answered.
        #expect(OnboardingFixtureEngine.unanswered.isEmpty, "unanswered: \(OnboardingFixtureEngine.unanswered)")
        #expect(setup.errorMessage == nil, "setup said: \(setup.errorMessage ?? "")")
        #expect(setup.name(of: "es") == "Spanish" && setup.name(of: "Latn") == "Latin", "the saved answers by name")
        for url in written {
            let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0
            #expect(size > 1000, "\(url.lastPathComponent) was drawn")
        }
        #expect(setup.recipe?.steps.first?.problem?.kind == "licence-not-accepted", "the fixture's licence step")
        #expect(setup.startPlan?.downloads?.first?.downloading == true, "the fixture's download under way")
    }
}
#endif
