//
//  ActivityLaunchAlertTests.swift
//  FicheroTests
//
//  #6584 `activity.launch.nothing-starts-one-alert`: the one alert at launch; its default leaves everything paused.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityLaunchAlertTests {
    @Test("the title counts, the message names at most five and says nothing runs")
    func titleAndMessage() {
        #expect(StoppedAtQuitAlert.title(count: 1) == "1 run was stopped when Fichero quit")
        #expect(StoppedAtQuitAlert.title(count: 3) == "3 runs were stopped when Fichero quit")
        let message = StoppedAtQuitAlert.message(names: ["Run the recipe: Letters", "Make thumbnails"])
        #expect(message.hasPrefix("Run the recipe: Letters\nMake thumbnails\n"))
        #expect(message.contains("Nothing runs until you choose"))
        let many = StoppedAtQuitAlert.message(names: (1...7).map { "Run \($0)" })
        #expect(many.contains("and 2 more"))
        #expect(!many.contains("Run 6"))
    }

    @Test("automatic work rolls into one line and a held folder read into another; the title counts the runs alone")
    func rollups() {
        let message = StoppedAtQuitAlert.message(items: [
            ("Run the recipe: Letters", "run-a-recipe"),
            ("Make thumbnails", "thumbnail"), ("Make thumbnails", "thumbnail"), ("Embed for search", "embedding"),
            ("Read a synced folder", "read-from-folder")
        ])
        #expect(message.hasPrefix("Run the recipe: Letters\n"))
        #expect(message.contains("and background work: 1 embeds, 2 thumbnails"))
        #expect(message.contains("New files in a synced folder"))
        #expect(!message.contains("Make thumbnails"), "no row per thumbnail")
    }

    @Test("Leave Paused, the default, dismisses and sends nothing; with nothing stopped the alert never shows")
    func leavePausedIsTheDefault() async {
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [])
        #expect(!alert.isPresented)
        alert.leavePaused()
        #expect(!alert.isPresented && alert.items.isEmpty)
    }
}
