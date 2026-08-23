//
//  CanvasJumpHistoryTests.swift
//  FicheroTests
//
//  §16 / R10 step 4 — the camera cuts, the user never flies. A jump-cut is only
//  cheap if you can get back from it, so zoom-to-fit (⌘=), jump back (⌘[) and
//  jump forward (⌘]) are one feature: a bounded Back/Forward stack of camera
//  poses, per window, saved nowhere.
//
//  Tested with Int poses on purpose. The type is generic because 2D and 3D
//  describe a camera differently, and the stack's behaviour has nothing to do
//  with either — testing it through a renderer would test RealityKit instead.
//

@testable import Fichero
import Foundation
import Testing

@Suite("CanvasJumpHistory (§16, R10 step 4)")
struct CanvasJumpHistoryTests {

    @Test("a fresh history goes nowhere, and says so")
    func emptyHistory() {
        var history = CanvasJumpHistory<Int>()
        #expect(!history.canJumpBack)
        #expect(!history.canJumpForward)
        // An empty back is a NO-OP, never a jump to the origin: a user pressing
        // ⌘[ on arrival must not have the camera yanked somewhere they have
        // never been.
        #expect(history.jumpBack(from: 7) == nil)
        #expect(history.jumpForward(from: 7) == nil)
        #expect(history.count == 0)
    }

    @Test("record then back returns exactly where you were")
    func backReturnsThePose() {
        var history = CanvasJumpHistory<Int>()
        history.record(1)          // was at 1, jumping to 2
        #expect(history.canJumpBack)
        #expect(history.jumpBack(from: 2) == 1)
        #expect(!history.canJumpBack)
        #expect(history.canJumpForward)
    }

    @Test("back and forward are symmetric — you can walk the path both ways")
    func backAndForwardAreSymmetric() {
        var history = CanvasJumpHistory<Int>()
        history.record(1)
        history.record(2)
        #expect(history.jumpBack(from: 3) == 2)
        #expect(history.jumpBack(from: 2) == 1)
        #expect(!history.canJumpBack)
        #expect(history.jumpForward(from: 1) == 2)
        #expect(history.jumpForward(from: 2) == 3)
        #expect(!history.canJumpForward)
    }

    @Test("a new jump after going back truncates the forward branch — the browser rule")
    func newJumpTruncatesForward() {
        // Once you go back and then somewhere NEW, the path you abandoned is
        // not somewhere ⌘] can return you to; pretending otherwise lands the
        // camera where the user has never been.
        var history = CanvasJumpHistory<Int>()
        history.record(1)
        history.record(2)
        #expect(history.jumpBack(from: 3) == 2)
        #expect(history.canJumpForward)

        history.record(2)          // a new jump from 2 to somewhere else
        #expect(!history.canJumpForward)
        #expect(history.jumpBack(from: 9) == 2)
    }

    @Test("the stack is bounded: the oldest pose falls off, the newest never does")
    func boundedToCapacity() {
        // An unbounded stack is a leak with good manners.
        var history = CanvasJumpHistory<Int>()
        for pose in 0..<(CanvasJumpHistory<Int>.capacity + 15) {
            history.record(pose)
        }
        #expect(history.count == CanvasJumpHistory<Int>.capacity)

        // The most recent pose is still the first one back.
        let newest = CanvasJumpHistory<Int>.capacity + 14
        #expect(history.jumpBack(from: 999) == newest)

        // Walking all the way back never hands out a pose that was dropped.
        var walked: [Int] = []
        var cursor = 999
        while let previous = history.jumpBack(from: cursor) {
            walked.append(previous)
            cursor = previous
        }
        #expect(walked.allSatisfy { $0 >= 15 })
        #expect(!history.canJumpBack)
    }

    @Test("the forward branch is bounded too")
    func forwardIsBounded() {
        var history = CanvasJumpHistory<Int>()
        for pose in 0..<CanvasJumpHistory<Int>.capacity {
            history.record(pose)
        }
        var cursor = 999
        while let previous = history.jumpBack(from: cursor) { cursor = previous }
        #expect(history.count <= CanvasJumpHistory<Int>.capacity)
    }

    @Test("poses are opaque: any renderer's camera description works")
    func genericOverThePose() {
        // 3D remembers look-at plus distance; 2D remembers a plane position and
        // an ortho scale. Neither has to flatten into the other's vocabulary.
        struct Pose3D: Equatable { let lookAt: [Float]; let distance: Float }
        var history = CanvasJumpHistory<Pose3D>()
        let start = Pose3D(lookAt: [1, 2, 3], distance: 6)
        history.record(start)
        #expect(history.jumpBack(from: Pose3D(lookAt: [9, 9, 9], distance: 2)) == start)
    }
}

// MARK: - It is view state, and it stays that way

/// The per-window ruling, as a test: a camera pose is where a window is
/// looking, which is not a fact about the library. If this type ever learns to
/// persist, two windows on one folder start fighting over "the" camera and
/// closing a window starts mattering.
struct CanvasJumpHistoryScopeGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    @Test("history touches no store, no defaults, no disk")
    func historyIsWindowLocal() throws {
        let source = try appSource("Views/Library/ViewModes/Canvas/Engine/CanvasJumpHistory.swift")
        for forbidden in ["UserDefaults", "AppStorage", "CanvasLayoutStore", "SceneStorage", "FileManager"] {
            #expect(!source.contains(forbidden), "jump history reached for \(forbidden) — it is view state")
        }
    }
}

// MARK: - Menu wiring

/// ⌘= / ⌘[ / ⌘] exist so the jump-cut is discoverable rather than a chord you
/// have to be told about, and the section must not tease a user who is in List
/// view. Only a source scan can see either property.
struct CanvasCameraCommandGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private var menuPath: String { "App/Menus/CanvasMenuCommands.swift" }

    private let canvases = [
        ["Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift",
         "Views/Library/ViewModes/Canvas/2D/CanvasSceneView+Gestures.swift"],
        ["Views/Library/ViewModes/Canvas/3D/CanvasSpaceView.swift",
         "Views/Library/ViewModes/Canvas/3D/CanvasSpaceView+Gestures.swift"],
    ]

    private func combined(_ paths: [String]) throws -> String {
        try paths.map { try appSource($0) }.joined(separator: "\n")
    }

    @Test("the keys are the ones surveyed as free, on the commands they belong to")
    func shortcutsAreBound() throws {
        let source = try appSource(menuPath)
        #expect(source.contains("Zoom to Fit"))
        #expect(source.contains(".keyboardShortcut(\"=\", modifiers: [.command])"))
        #expect(source.contains(".keyboardShortcut(\"[\", modifiers: [.command])"))
        #expect(source.contains(".keyboardShortcut(\"]\", modifiers: [.command])"))
    }

    @Test("the Canvas section disables itself when no canvas is focused")
    func sectionIsDisabledOffCanvas() throws {
        // Dead-simple-UX: a control that cannot apply should not tease. The
        // FocusedValue is nil outside a canvas, and every button follows the
        // house disabled-when-nil pattern rather than relying on that alone.
        let source = try appSource(menuPath)
        #expect(source.contains("private var hasFocusedCanvas: Bool { canvasActions != nil }"))
        #expect(source.components(separatedBy: ".disabled(!hasFocusedCanvas").count - 1 == 3)
        // And the two history commands are dead until there is somewhere to go.
        #expect(source.contains("canvasActions?.canJumpBack != true"))
        #expect(source.contains("canvasActions?.canJumpForward != true"))
    }

    @Test("the section is in the View menu, where a view command belongs")
    func sectionIsInTheViewMenu() throws {
        #expect(try appSource("App/Menus/ViewMenuCommands.swift").contains("CanvasViewSection()"))
    }

    @Test("the payload compares FLAGS only — closures would republish every frame")
    func equatableComparesFlagsOnly() throws {
        // The ×31 "FocusedValue update tried to update multiple times per
        // frame" fault in the 2026-08-19 log came from exactly this.
        let source = try appSource("App/Menus/FocusedCommandButtons+FocusedValues.swift")
        let tail = try #require(source.components(separatedBy: "struct CanvasViewActions").last)
        let body = try #require(tail.components(separatedBy: "\nstruct ").first)
        #expect(body.contains("lhs.canJumpBack == rhs.canJumpBack && lhs.canJumpForward == rhs.canJumpForward"))
        #expect(!body.contains("lhs.zoomToFit"))
    }

    @Test("both canvases publish the commands and record poses at the jump sites")
    func bothCanvasesPublish() throws {
        for paths in canvases {
            let source = try combined(paths)
            #expect(source.contains("focusedSceneValue(\\.canvasViewActions, canvasCommandActions)"),
                    "\(paths) does not publish its camera commands")
            // Recorded on the jumps worth returning from — zoom-to-fit and the
            // double-click focus — and NOWHERE else: a pose per pan frame would
            // fill the stack with places nobody chose to go.
            #expect(source.components(separatedBy: "jumpHistory.record(").count - 1 == 2,
                    "\(paths) records a pose somewhere other than the two jump sites")
            #expect(source.contains("jumpHistory.jumpBack(from: renderer.cameraSnapshot())"))
            #expect(source.contains("jumpHistory.jumpForward(from: renderer.cameraSnapshot())"))
        }
    }

    @Test("no fly: the camera cuts, and nothing animates it between poses")
    func nothingFlies() throws {
        // R10 is explicit. `restoreCamera` sets a pose outright; if a jump ever
        // grows an easing path, this is where that decision has to be made
        // rather than discovered.
        for paths in canvases {
            let source = try combined(paths)
            #expect(!source.contains("withAnimation") || !source.contains("restoreCamera"))
        }
    }
}
