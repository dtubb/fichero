#if os(macOS)
import Cocoa
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppleScript")

// The UI verbs as AppleScript commands (#5453, `openapi.ui.verbs-are-the-click`): each is one `UIVerbs`
// call, the same one its App Intent makes. A refusal sets the script error, so osascript reports it.

/// The shared shape: run `body` on the main actor, turning a thrown error into the script's error.
private extension NSScriptCommand {
    nonisolated func runVerb<T: Sendable>(_ verb: String, _ body: @MainActor () throws -> T) -> Any? {
        logger.info("AppleScript: \(verb, privacy: .public)")
        do {
            return try MainActor.assumeIsolated(body)
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }

    /// The direct parameter as text, or a script error naming what was missing.
    nonisolated func requiredText(_ what: String) -> String? {
        guard let text = directParameter as? String, !text.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "\(what) is required"
            return nil
        }
        return text
    }

    /// The direct parameter as a list of text (one text is a list of one).
    nonisolated var textList: [String] {
        if let one = directParameter as? String { return [one] }
        return (directParameter as? [Any])?.compactMap { $0 as? String } ?? []
    }
}

/// `open project "<path>"`: File ▸ Open in the front window. Answers the project's id.
@objc(FicheroOpenProjectCommand)
class FicheroOpenProjectCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let path = requiredText("Project path") else { return nil }
        return runVerb("open project \(path)") {
            NSApplication.shared.activate()
            return UIVerbs.openProject(at: URL(fileURLWithPath: (path as NSString).expandingTildeInPath)).uuidString
        }
    }
}

/// `open node "<id>"`: the node opened, as clicking it opens it.
@objc(FicheroOpenNodeCommand)
class FicheroOpenNodeCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let id = requiredText("Node id") else { return false }
        return runVerb("open node \(id)") {
            UIVerbs.openNode(id)
            return true
        }
    }
}

/// `select nodes {"<id>", ...}`: the Library's selection, as clicking the nodes sets it.
@objc(FicheroSelectNodesCommand)
class FicheroSelectNodesCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        let ids = textList
        return runVerb("select nodes \(ids)") {
            try UIVerbs.selectNodes(ids)
            return true
        }
    }
}

/// `reveal segments {"<id>", ...} in page "<id>"`: selected and zoomed to in the linked Preview. Answers the ids revealed.
@objc(FicheroRevealSegmentsCommand)
class FicheroRevealSegmentsCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        let ids = textList
        guard let page = evaluatedArguments?["documentId"] as? String, !page.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "The page id (in page) is required"
            return nil
        }
        return runVerb("reveal segments \(ids) in page \(page)") {
            try UIVerbs.revealSegments(ids, documentId: page)
        }
    }
}

/// `show pane "<name>"`: library, preview, reader, inspector, activity, chat or segments.
@objc(FicheroShowPaneCommand)
class FicheroShowPaneCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let name = requiredText("Pane name") else { return false }
        return runVerb("show pane \(name)") {
            guard let pane = UIPane(named: name) else { throw UIVerbs.Failure.unknownPane(name) }
            try UIVerbs.showPane(pane)
            return true
        }
    }
}

/// `show inspector tab "<name>"`: the Inspector shown at that tab.
@objc(FicheroShowInspectorTabCommand)
class FicheroShowInspectorTabCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let name = requiredText("Tab name") else { return false }
        return runVerb("show inspector tab \(name)") {
            guard let tab = InspectorTab(named: name) else { throw UIVerbs.Failure.unknownInspectorTab(name) }
            try UIVerbs.showInspectorTab(tab)
            return true
        }
    }
}
#endif
