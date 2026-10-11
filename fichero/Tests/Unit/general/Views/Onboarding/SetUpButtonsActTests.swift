//
//  SetUpButtonsActTests.swift
//  FicheroTests
//
//  #5660 item 2 (the maintainer's Set Up test of 2026.10.10): "Review the licence…" did nothing. Every Set Up
//  button acts, or is disabled with its reason. These pin it two ways: no Set Up view draws a Button whose action
//  is empty, and every fix the engine can send routes somewhere that acts.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
@Suite(.serialized)
struct SetUpButtonsActTests {
    /// The Set Up views: every Swift file of the setup window.
    private static func setUpSources() throws -> [(name: String, text: String)] {
        let folder = try AppSource.root().appendingPathComponent("Views/Onboarding")
        let files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "swift" }
        return try files.map { ($0.lastPathComponent, try String(contentsOf: $0, encoding: .utf8)) }
    }

    /// A Button whose action does nothing: `Button("…") {}`, `Button("…", action: {})`, `Button(action: {})`.
    nonisolated static func emptyActions(in source: String) -> [String] {
        let patterns = [
            #"Button\((?:"[^"\n]*"|[^(){}\n]*)\)\s*\{\s*\}"#,
            #"Button\([^\n]*action:\s*\{\s*\}"#
        ]
        return patterns.flatMap { pattern -> [String] in
            guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
            let range = NSRange(source.startIndex..., in: source)
            return regex.matches(in: source, range: range).compactMap { Range($0.range, in: source).map { String(source[$0]) } }
        }
    }

    @Test("the check itself catches a button with an empty action")
    func theCheckCatchesAnEmptyButton() {
        // WHY: a guard that never fires proves nothing; it must see the dead button shapes it exists for.
        #expect(Self.emptyActions(in: #"Button("Review the licence…") {}"#).count == 1)
        #expect(Self.emptyActions(in: #"Button("Done", action: {})"#).count == 1)
        #expect(Self.emptyActions(in: #"Button(title) { }"#).count == 1)
        #expect(Self.emptyActions(in: #"Button("Start") { Task { await store.start() } }"#).isEmpty)
    }

    @Test("no Set Up button has an empty action")
    func noSetUpButtonIsEmpty() throws {
        // WHY: a press that does nothing reads as a broken app; a button that cannot act is disabled with why.
        let sources = try Self.setUpSources()
        #expect(sources.count >= 8, "the Set Up views were found")
        for (name, text) in sources {
            #expect(Self.emptyActions(in: text).isEmpty, "\(name) draws a Button with an empty action")
        }
    }

    @Test("every fix the engine sends routes to something that acts")
    func everyFixActs() {
        // WHY: a step's fix button is drawn from the engine's `fix` (`StepProblem.fix`); "accept-licence" went to a
        // handler that opened nothing. With a project, each model fix opens the finder, the licence opens its review,
        // and letting pages leave is setup's own answer (`allowCloud`).
        for fix in ["choose-model", "download", "choose-cloud"] {
            #expect(RecipeStepsView.fixRoute(fix, hasProject: true) == .finder, "\(fix)")
        }
        #expect(RecipeStepsView.fixRoute("accept-licence", hasProject: true) == .licence)
        #expect(RecipeStepsView.fixRoute("allow-cloud", hasProject: true) == .setup)
        #expect(RecipeStepRow.fixTitle("accept-licence") == "Review the licence…")
    }

    @Test("Review the licence… lists the models refused for their licence, with the licence to read")
    func licenceReviewListsTheLicensedModels() throws {
        // WHY: the sheet must show the model the rules held back for its licence, name that licence and link to
        // its text, so accepting is an informed press.
        let candidates = try JSONDecoder().decode([Components.Schemas.ModelCandidate].self, from: Data("""
        [{"id":"mlx:hf:a@main","name":"Open reader","source":"shipped","offered_because":"ships",
          "pin":{},"jobs":["find-regions"],"open_licence":true,"size":"1 GB","measured":"unmeasured",
          "in_recipe_rules":true,"runs_where":"this_mac","availability":"ships","availability_words":"Ships with Fichero"},
         {"id":"yolo:hf:b@main","name":"Region finder","source":"shipped","offered_because":"fits",
          "pin":{},"jobs":["find-regions"],"licence":"agpl-3.0","open_licence":false,"size":"0.1 GB",
          "measured":"unmeasured","in_recipe_rules":true,"runs_where":"this_mac","availability":"ships","availability_words":"Ships with Fichero"},
         {"id":"yolo:hf:c@main","name":"Other closed","source":"shipped","offered_because":"fits",
          "pin":{},"jobs":["find-regions"],"licence":"Research use only","open_licence":false,"size":"0.1 GB",
          "measured":"unmeasured","in_recipe_rules":true,"runs_where":"this_mac","availability":"ships","availability_words":"Ships with Fichero"}]
        """.utf8))
        let named = LicenceReviewSheet.licensed(candidates, refused: ["yolo:hf:b@main"])
        #expect(named.map(\.name) == ["Region finder"])
        #expect(LicenceReviewSheet.licensed(candidates, refused: []).map(\.name) == ["Region finder", "Other closed"])
        #expect(LicenceReviewSheet.licenceName(named[0]) == "agpl-3.0")
        #expect(LicenceReviewSheet.licenceURL("agpl-3.0")?.absoluteString == "https://spdx.org/licenses/agpl-3.0.html")
        #expect(LicenceReviewSheet.licenceURL("Research use only") == nil)
    }

    @Test("a disabled Start says why")
    func disabledStartSaysWhy() {
        // WHY: Start disabled with no reason reads as broken; its help names the plan's first refusal.
        let store = RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                           libraryPath: "/tmp/test.fichero"))
        #expect(store.startDisabledReason == "Fichero is still planning what Start would run.")
    }
}
