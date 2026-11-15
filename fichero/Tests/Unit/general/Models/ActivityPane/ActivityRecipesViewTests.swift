@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.window.recipes` (#6588, decision 37): recipe › run › step, with the rates that compare runs, from the engine.
struct ActivityRecipesViewTests {
    private func recipes() throws -> [Components.Schemas.RecipeRow] {
        let json = """
        {"recipes": [{"id": "wf", "name": "Read the letters", "run_count": 2, "pages_done": 37, "pages_failed": 3,
          "failed_pct": 7.5, "seconds_per_page": 4.0, "last_run": "2026-11-15T14:00:00.000000+00:00",
          "runs": [
            {"id": "run-qwen", "status": "completed", "pages_done": 20, "pages_failed": 0, "failed_pct": 0.0,
             "seconds_per_page": 4.0, "cost_per_page": 0.0, "started_at": "2026-11-15T14:00:00+00:00",
             "steps": [{"id": "read", "name": "Read", "model": "ollama:qwen2-vl", "pages_done": 20, "pages_failed": 0,
                        "seconds_per_page": 4.0}]},
            {"id": "run-kraken", "status": "completed", "pages_done": 17, "pages_failed": 3, "failed_pct": 15.0,
             "seconds_per_page": 95.0, "started_at": "2026-11-15T13:00:00+00:00",
             "steps": [{"id": "read", "name": "Read", "model": "kraken:catmus", "pages_done": 17, "pages_failed": 3}]}]}]}
        """
        return try JSONDecoder().decode(Components.Schemas.ActivityRecipesResponse.self, from: Data(json.utf8)).recipes ?? []
    }

    @Test("a recipe opens to its runs, newest first, and each run to its steps with their model")
    func outline() throws {
        let lines = ActivityRecipeLine.lines(try recipes())
        let recipe = try #require(lines.first)
        #expect(recipe.level == .recipe && recipe.runs == 2 && recipe.when != nil)
        let runs = try #require(recipe.children)
        #expect(runs.map(\.id) == ["run:run-qwen", "run:run-kraken"])
        #expect(runs[0].model == "ollama:qwen2-vl" && runs[1].model == "kraken:catmus")
        #expect(runs[1].children?.first?.failedWords == "15%")
    }

    @Test("rates read short: 15%, 4 s, 1.6 min, Free at zero, blank when unknown")
    func words() throws {
        let runs = try #require(ActivityRecipeLine.lines(try recipes()).first?.children)
        #expect(runs[0].failedWords == "0%" && runs[1].failedWords == "15%")
        #expect(runs[0].perPageWords == "4 s" && runs[1].perPageWords == "1.6 min")
        #expect(runs[0].costWords == "Free" && runs[1].costWords == "")
    }
}
