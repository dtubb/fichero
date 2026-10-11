import Foundation
import Observation
import SwiftUI

/// What takes a step back: the project's actions service (`undoSet`), or a test's fake engine.
@MainActor
protocol UndoSetEngine: AnyObject {
    /// The project the steps belong to, by its package path.
    var projectPath: String? { get }
    /// Take back several steps together, all or none; the rows the reversal wrote.
    func undoSet(auditIds: [String]) async throws -> [String]
}

extension ActionLibraryService: UndoSetEngine {
    var projectPath: String? { client.currentLibraryPath }
}

/// One window's step stack (`undo.window`, `undo.window.own-stack`, #5658, ruled per window
/// 2026-10-11): the changes a person made in THIS window, newest first, each held as the audit rows
/// it wrote, never as data or a closure that writes.
///
/// It owns its own `UndoManager`, apart from the one text fields use for typing, so typing and
/// project steps never share a stack. A step remembers its project by path and finds that project's
/// live service when it is taken back, not when it was made, so it survives an engine restart and a
/// window that switched project. While one of its calls is out, Undo and Redo wait
/// (`undo.window.in-flight`). A refusal is kept here for the window to show
/// (`UndoRefusalNotice`).
@MainActor
@Observable
final class WindowSteps {
    let undoManager: UndoManager = {
        let manager = UndoManager()
        // Grouped by hand: steps are registered after awaits, outside any event.
        manager.groupsByEvent = false
        return manager
    }()

    /// Engine calls this window's steps have out (a change, an undo, a redo).
    private(set) var inFlight = 0
    /// The engine's last refusal in this window, for the notice; cleared when it is dismissed.
    var refusal: String?
    /// Bumped on every change of the stack, so a view observing it re-reads the titles.
    private(set) var revision = 0

    /// The live service for a project path, looked up when a step is taken back.
    @ObservationIgnored var engineForProject: @MainActor (String) -> (any UndoSetEngine)? = { path in
        LibraryManager.shared.openLibraries.first { $0.url.path == path }?.actionsService
    }

    /// What it takes to file a step again: its name, its project, its hooks and its reversal.
    private final class Recipe {
        let name: String
        let project: String
        var hooks = ActionUndo.Hooks()
        var perform: @MainActor ([String]) async throws -> [String] = { $0 }
        init(name: String, project: String) {
            self.name = name
            self.project = project
        }
    }

    /// A step on the undo side, with its recipe.
    private struct Filed {
        let handle: ActionUndo.Handle
        let recipe: Recipe
    }

    /// The steps registered in this window that have not ended, held so their hooks can file them again.
    @ObservationIgnored private var recipes: [Recipe] = []
    /// The undo side of the stack, bottom to top. An UndoManager cannot take one group out of the middle
    /// (`removeAllActions(withTarget:)` leaves the group, empty and still named), so ending a project's
    /// steps rebuilds the stack from this.
    @ObservationIgnored private var undoSide: [Filed] = []
    /// The newest step's rows, so a commit the engine folded into the same rows is not a second step.
    @ObservationIgnored private var newestIds: [String] = []

    /// Every live window's steps, so closing a project or signing out ends them everywhere.
    private static let all = NSHashTable<WindowSteps>.weakObjects()

    init() { Self.all.add(self) }

    var canUndo: Bool { inFlight == 0 && undoManager.canUndo }
    var canRedo: Bool { inFlight == 0 && undoManager.canRedo }
    /// "Move", "Delete 3 Items": the step's own words, for the Edit menu.
    var undoName: String? { undoManager.canUndo ? undoManager.undoActionName.nilIfEmpty : nil }
    var redoName: String? { undoManager.canRedo ? undoManager.redoActionName.nilIfEmpty : nil }

    func undo() { guard canUndo else { return }; undoManager.undo(); revision += 1 }
    func redo() { guard canRedo else { return }; undoManager.redo(); revision += 1 }

    /// A call this window started is out, or back (`undo.window.in-flight`).
    func callStarted() { inFlight += 1 }
    func callEnded() { inFlight = max(0, inFlight - 1); revision += 1 }

    /// Register one step holding `auditIds`, made in `project` (by `fallback`'s path). Undo and redo
    /// take the rows back as a set through the project's live service.
    @discardableResult
    func register(
        _ auditIds: [String], named name: String, engine fallback: any UndoSetEngine,
        afterEach: @escaping @MainActor () async -> Void = {}
    ) -> ActionUndo.Handle? {
        let ids = auditIds.filter { !$0.isEmpty }
        guard !ids.isEmpty else { return nil }
        // `undo.typing.commit-is-one-step`: the same rows answered again are the step already on top.
        if ids == newestIds, undoManager.canUndo { return nil }
        let project = fallback.projectPath ?? ""
        let recipe = Recipe(name: name, project: project)
        recipe.hooks.willCall = { [weak self] in self?.callStarted() }
        recipe.hooks.didCall = { [weak self] in self?.callEnded() }
        recipe.hooks.didRegister = { [weak self, weak recipe] handle in
            guard let self, let recipe else { return }
            self.filed(handle, recipe: recipe)
        }
        recipe.hooks.didRemove = { [weak self] handle in self?.undoSide.removeAll { $0.handle === handle } }
        recipe.hooks.onRefusal = { [weak self] error in self?.refusal = error.localizedDescription }
        // The service it was made through is kept as the fallback: a closed project's steps were ended
        // when it closed, so the live lookup only misses for a surface outside the open projects.
        recipe.perform = { [weak self] rows in
            let engine = self?.engineForProject(project) ?? fallback
            let written = try await engine.undoSet(auditIds: rows)
            // A surface that does not yet follow the change stream re-reads what the step changed.
            await afterEach()
            return written
        }
        recipes.append(recipe)
        let handle = ActionUndo.registerSet(
            auditIds: ids, actionName: name, undoManager: undoManager, hooks: recipe.hooks,
            performUndo: recipe.perform
        )
        newestIds = ids
        revision += 1
        return handle
    }

    /// A step was filed. Filed while undoing, it is that undo's redo (the redo side is not rebuilt), and
    /// the step undone has left the top of the undo side; otherwise it is on the undo side, on top.
    private func filed(_ handle: ActionUndo.Handle, recipe: Recipe) {
        if undoManager.isUndoing {
            _ = undoSide.popLast()
        } else {
            undoSide.append(Filed(handle: handle, recipe: recipe))
        }
    }

    /// End this window's steps in one project (closed, or returned to a snapshot); the others stay, in
    /// their order. The redo side does not survive the rebuild.
    func endSteps(forProject path: String) {
        // A window with no step in that project keeps its whole stack, redo side included: closing one project must
        // not take Redo away from a window working in another (nor, under test, from every other test's window).
        guard recipes.contains(where: { $0.project == path }) else { return }
        let kept = undoSide.filter { $0.recipe.project != path }
        recipes.removeAll { $0.project == path }
        undoManager.removeAllActions()
        undoSide = []
        newestIds = []
        for step in kept {
            ActionUndo.reschedule(
                step.handle, actionName: step.recipe.name, undoManager: undoManager, hooks: step.recipe.hooks,
                performUndo: step.recipe.perform
            )
        }
        revision += 1
    }

    /// End every step (signed out, or another person signed in).
    func endAllSteps() {
        undoManager.removeAllActions()
        recipes = []
        undoSide = []
        newestIds = []
        revision += 1
    }

    /// A project closed or went back to a snapshot: its steps end in every window.
    static func endSteps(forProject path: String) {
        for steps in all.allObjects { steps.endSteps(forProject: path) }
    }

    /// The person signed out: every window's steps end.
    static func endAllSteps() {
        for steps in all.allObjects { steps.endAllSteps() }
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

// MARK: - Where views find it

/// The key window's steps, for the Edit menu.
struct WindowStepsFocusedKey: FocusedValueKey {
    typealias Value = WindowSteps
}

extension FocusedValues {
    var windowSteps: WindowSteps? {
        get { self[WindowStepsFocusedKey.self] }
        set { self[WindowStepsFocusedKey.self] = newValue }
    }
}
