//
//  StartFreshTests.swift
//  FicheroTests
//
//  Shift at launch starts with nothing open (maintainer, 2026-10-09; #5628): the saved open-project list
//  and the window layout keys are forgotten, other settings stay, and AppKit is told not to restore windows.
//

@testable import Fichero
import Testing
import Foundation

@MainActor
struct StartFreshTests {
    @Test func resetForgetsOpenProjectsAndLayoutButKeepsOtherSettings() throws {
        let suite = "StartFreshTests-\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(["/tmp/A.fichero"], forKey: LibraryManager.openLibraryPathsKey)
        defaults.set("0 0 800 600", forKey: "NSWindow Frame main-AppWindow-1")
        defaults.set(["a"], forKey: "NSSplitView Subview Frames sidebar")
        defaults.set(true, forKey: "SomeUserPreference")

        StartFresh.reset(standard: defaults, appDefaults: defaults)

        #expect(defaults.object(forKey: LibraryManager.openLibraryPathsKey) == nil)
        #expect(defaults.object(forKey: "NSWindow Frame main-AppWindow-1") == nil)
        #expect(defaults.object(forKey: "NSSplitView Subview Frames sidebar") == nil)
        #expect(defaults.bool(forKey: "SomeUserPreference"))
        #expect(defaults.bool(forKey: StartFresh.ignoreSavedStateKey))
    }

    @Test func onlyLayoutKeysCount() {
        #expect(StartFresh.isLayoutKey("NSWindow Frame Settings"))
        #expect(!StartFresh.isLayoutKey("FicheroOpenLibraryPaths"))
        #expect(!StartFresh.isLayoutKey("AppleLanguages"))
    }
}
