@testable import Fichero
import Foundation
import Testing

/// #4703: the app trapped ~25s after launch with "No Observable object of
/// type WorkflowExecutionObserver found". The trap is a CLASS, not one type:
/// toolbar items (each hosted in its own hosting view, #4448) and the
/// inspector column do NOT inherit the window's SwiftUI environment, so any
/// `@Environment(<T>.self)` read there of an app `@Observable` class is a
/// non-optional read of a value the scene never injected into that boundary.
/// Fix 48498334c made six `WorkflowExecutionObserver` readers optional
/// (`: WorkflowExecutionObserver?`) but left the CLASS of bug in place —
/// every other `@Environment(<Observable>.self)` read under the same three
/// boundaries (toolbar, inspector, workflow inspector) is exactly as trap-prone.
///
/// This guardrail pins the rule going forward (no NEW non-optional read may
/// land under these directories) while tracking today's pre-existing debt in
/// a SHRINKING allowlist — each entry needs a `#4703 follow-up` issue and a
/// fix; the allowlist test below fails the moment an entry is fixed, so a fix
/// forces its removal rather than leaving a stale, silently-passing pin.
struct EnvironmentOptionalObservableGuardrailTests {

    // MARK: - Discover every app `@Observable` class

    /// Every `class Name` immediately (within ~200 chars, across attributes/
    /// doc comments) preceded by `@Observable` anywhere under the app target.
    /// This is what makes "app @Observable class" a computed set rather than
    /// a hand-maintained list that drifts the moment a new store is added.
    private static func observableClassNames(root: URL) throws -> Set<String> {
        let classAfterObservable = try NSRegularExpression(
            pattern: #"@Observable\b[\s\S]{0,200}?\bclass\s+([A-Za-z0-9_]+)"#
        )
        var names: Set<String> = []
        guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil) else {
            return names
        }
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            guard let source = try? String(contentsOf: url, encoding: .utf8) else { continue }
            let ns = source as NSString
            for match in classAfterObservable.matches(in: source, range: NSRange(location: 0, length: ns.length)) {
                let range = match.range(at: 1)
                if range.location != NSNotFound {
                    names.insert(ns.substring(with: range))
                }
            }
        }
        return names
    }

    // MARK: - Scan for non-optional `@Environment(<Observable>.self)` reads

    struct Violation {
        let file: String
        let line: Int
        let type: String
        let property: String
        var key: String { "\(file):\(line) \(type)->\(property)" }
    }

    /// A `@Environment(Type.self)` mint whose property declaration — on the
    /// same line, or the next non-comment/non-blank line (the doc-commented,
    /// annotation-on-its-own-line style used throughout this app) — has no
    /// `?` anywhere, for a `Type` in `observable`.
    private static func nonOptionalObservableReads(
        underRelativeDirs relativeDirs: [String],
        root: URL,
        observable: Set<String>
    ) throws -> [Violation] {
        let envMint = try NSRegularExpression(pattern: #"@Environment\(([A-Za-z0-9_]+)\.self\)"#)
        let varName = try NSRegularExpression(pattern: #"\bvar\s+(\w+)"#)
        var results: [Violation] = []

        for relativeDir in relativeDirs {
            let dirURL = root.appendingPathComponent(relativeDir)
            guard let enumerator = FileManager.default.enumerator(at: dirURL, includingPropertiesForKeys: nil) else {
                continue
            }
            for case let fileURL as URL in enumerator where fileURL.pathExtension == "swift" {
                guard let source = try? String(contentsOf: fileURL, encoding: .utf8) else { continue }
                let relative = AppSource.relativePath(of: fileURL, under: root)
                let lines = source.components(separatedBy: "\n")

                for (index, line) in lines.enumerated() {
                    let lineNS = line as NSString
                    guard let mintMatch = envMint.firstMatch(
                        in: line, range: NSRange(location: 0, length: lineNS.length)
                    ) else { continue }
                    let type = lineNS.substring(with: mintMatch.range(at: 1))
                    guard observable.contains(type) else { continue }

                    let tailStart = mintMatch.range.location + mintMatch.range.length
                    let tail = lineNS.substring(from: tailStart)
                    var declLine: String?
                    if tail.range(of: #"\bvar\s+\w+"#, options: .regularExpression) != nil {
                        declLine = line
                    } else {
                        var lookahead = index + 1
                        while lookahead < lines.count {
                            let trimmed = lines[lookahead].trimmingCharacters(in: .whitespaces)
                            if trimmed.isEmpty || trimmed.hasPrefix("///") || trimmed.hasPrefix("//") {
                                lookahead += 1
                                continue
                            }
                            break
                        }
                        if lookahead < lines.count { declLine = lines[lookahead] }
                    }
                    guard let decl = declLine, !decl.contains("?") else { continue }

                    let declNS = decl as NSString
                    let property: String
                    if let nameMatch = varName.firstMatch(in: decl, range: NSRange(location: 0, length: declNS.length)) {
                        property = declNS.substring(with: nameMatch.range(at: 1))
                    } else {
                        property = "?"
                    }
                    results.append(Violation(file: relative, line: index + 1, type: type, property: property))
                }
            }
        }
        return results
    }

    private static let scannedDirectories = [
        "Views/Shell/Toolbar",
        "Views/Inspector",
        "Views/Workflow/Inspector",
    ]

    /// Pre-existing debt as of 2026-09-18, audited alongside 48498334c: every
    /// one of these is a REAL non-optional `@Environment(<Observable>.self)`
    /// read under a boundary that does not inherit the window's SwiftUI
    /// environment, so every one is exactly as trap-prone as the six
    /// `WorkflowExecutionObserver` reads that fix already made optional.
    /// #4703 follow-up: each needs an issue and a fix that removes it below.
    /// SHRINK ONLY — `allowlistEntriesStillViolate` fails the moment an entry
    /// stops violating, so a fix must delete the entry, not leave it stale.
    private static let allowlist: Set<String> = [
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactEntityViews.swift:201 ArtifactService->artifactService",
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactEntityViews.swift:26 ArtifactService->artifactService",
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:75 ArtifactStore->store",
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:76 ArtifactService->artifactService",
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:77 DocumentService->documentService",
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:78 DocumentStore->documentStore",
        // #4703 follow-up
        "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:79 LibraryManager->libraryManager",
        // #4703 follow-up
        "Views/Inspector/DisplayAttributesStrip.swift:16 ArtifactStore->artifactStore",
        // #4703 follow-up
        "Views/Inspector/DisplayAttributesStrip.swift:48 EntityService->entityService",
        // #4703 follow-up
        "Views/Inspector/DisplayAttributesStrip.swift:56 EntityStore->entityStore",
        // #4703 follow-up
        "Views/Inspector/DisplayAttributesStrip.swift:57 ClaimStore->claimStore",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector+Sections.swift:125 APIClient->apiClient",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector+Sections.swift:126 StorageService->storageService",
        // #4703 follow-up
        // #4902: line pins re-synced to source (+3, unrelated growth above them)
        "Views/Inspector/Document/DocumentInspector.swift:76 DocumentStore->documentStore",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector.swift:77 EntityService->entityService",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector.swift:78 ArtifactService->artifactService",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector.swift:79 KGCurationService->kgCurationService",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector.swift:80 ClaimFocusState->claimFocusState",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspector.swift:84 KGFocusState->kgFocusState",
        // #4703 follow-up
        "Views/Inspector/Document/DocumentInspectorRelatedTab.swift:17 DocumentStore->documentStore",
        // #4703 follow-up
        "Views/Inspector/FocusedDocument.swift:36 LibraryManager->libraryManager",
        // #4703 follow-up
        "Views/Inspector/FocusedDocument.swift:37 ClaimFocusState->claimFocusState",
        // #4703 follow-up
        "Views/Inspector/FocusedDocument.swift:38 KGFocusState->kgFocusState",
        // #4703 follow-up
        "Views/Inspector/Knowledge/Citations/CitationsInspectorPane.swift:18 CitationStore->store",
        // #4703 follow-up
        "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift:31 EntityStore->entityStore",
        // #4703 follow-up
        "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift:32 EntityService->entityService",
        // #4703 follow-up
        "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift:36 KGFocusState->kgFocusState",
        // #4703 follow-up
        "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift:38 DocumentStore->documentStore",
        // #4703 follow-up
        "Views/Inspector/Knowledge/EntityDigestView.swift:8 EntityStore->entityStore",
        // #4703 follow-up
        "Views/Inspector/Knowledge/EntityDigestView.swift:9 EntityService->entityService",
        // #4703 follow-up
        // #4902: line pins re-synced to source (+5, unrelated growth above them)
        "Views/Inspector/Knowledge/EntityKindRow.swift:50 ClaimFocusState->claimFocusState",
        // #4703 follow-up
        "Views/Inspector/Knowledge/EntityKindRow.swift:51 KGFocusState->kgFocusState",
        // #4703 follow-up
        "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift:43 KGFocusState->kgFocusState",
        // #4703 follow-up
        "Views/Inspector/Knowledge/KnowledgeGraph/KnowledgeGraphInspectorSection.swift:52 ClaimStore->claimStore",
        // #4703 follow-up
        "Views/Inspector/Notes/Annotations/AnnotationsInspectorPane.swift:12 AnnotationStore->annotationStore",
        // #4703 follow-up
        "Views/Inspector/Notes/DocumentInspectorAnnotationsTab.swift:7 AnnotationStore->annotationStore",
        // #4703 follow-up
        "Views/Inspector/Notes/DocumentInterpretationsSection.swift:10 InterpretationStore->store",
        // #4703 follow-up
        "Views/Inspector/Notes/DocumentNotesTab.swift:10 NoteStore->noteStore",
        // #4703 follow-up
        "Views/Inspector/Notes/NotesInspectorPane.swift:12 NoteStore->noteStore",
        // #4703 follow-up
        "Views/Inspector/Source/DocumentInspectorContentV2.swift:27 ArtifactStore->artifactStore",
        // #4703 follow-up
        "Views/Inspector/Source/DocumentInspectorContentV2.swift:28 DocumentService->documentService",
        // #4703 follow-up
        "Views/Inspector/Source/DocumentInspectorContentV2.swift:29 DocumentStore->documentStore",
        // #4703 follow-up
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Bibliography.swift:16 ReferenceStore->store",
        // #4703 follow-up
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Citations.swift:13 CitationStore->store",
        // #4703 follow-up
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Workflow.swift:12 EntityService->entityService",
        // #4703 follow-up
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift:10 DocumentStore->documentStore",
        // #4703 follow-up
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift:8 LibraryManager->libraryManager",
        // #4703 follow-up
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift:9 WindowState->windowState",
        // #4703 follow-up
        // #4902: line pin re-synced to source (+1)
        "Views/Inspector/Source/SourceOutlineView.swift:113 DocumentService->documentService",
        // #4703 follow-up
        "Views/Shell/Toolbar/ActivityStatusToolbarItem.swift:24 ActivityStore->activityStore",
        // #4703 follow-up
        "Views/Shell/Toolbar/EngineStatusToolbarItem.swift:37 AppState->appState",
        // #4703 follow-up
        "Views/Shell/Toolbar/ModelChipToolbarItem.swift:25 AppState->appState",
        // #4703 follow-up
        "Views/Shell/Toolbar/StatusIslandToolbarItem.swift:18 AppState->appState",
        // #4703 follow-up
        "Views/Shell/Toolbar/StatusIslandToolbarItem.swift:24 ActivityStore->activityStore",
        // #4703 follow-up
        "Views/Shell/Toolbar/WorkflowStepsDisclosure.swift:17 WorkflowStore->workflowStore",
        // #4703 follow-up
        "Views/Shell/Toolbar/WorkflowToolsPopover.swift:23 FeatureManager->featureManager",
        // #4703 follow-up
        "Views/Workflow/Inspector/WorkflowInspector.swift:22 WorkflowService->workflowService",
        // #4703 follow-up
        "Views/Workflow/Inspector/WorkflowInspector.swift:23 MCPService->mcpService",
        // #4703 follow-up
        "Views/Workflow/Inspector/WorkflowInspector.swift:24 AppState->appState",
        // #4703 follow-up
        "Views/Workflow/Inspector/WorkflowInspector.swift:26 WorkflowStore->workflowStore",
    ]

    @Test("no NEW non-optional @Environment(<Observable>.self) reads land under toolbar/inspector")
    func noNewViolationsBeyondTheAllowlist() throws {
        let root = try AppSource.root()
        let observable = try Self.observableClassNames(root: root)
        let found = try Self.nonOptionalObservableReads(
            underRelativeDirs: Self.scannedDirectories, root: root, observable: observable
        )
        let foundKeys = Set(found.map(\.key))
        let unexpected = foundKeys.subtracting(Self.allowlist)
        #expect(
            unexpected.isEmpty,
            "New non-optional @Environment(<Observable>.self) reads under Toolbar/Inspector/Workflow-Inspector — these boundaries do NOT inherit the window's SwiftUI environment (#4703) and a non-optional read there traps: \(unexpected.sorted().joined(separator: "; "))"
        )
    }

    @Test("the #4703 allowlist only shrinks — every entry must still be a real violation")
    func allowlistEntriesStillViolate() throws {
        let root = try AppSource.root()
        let observable = try Self.observableClassNames(root: root)
        let found = try Self.nonOptionalObservableReads(
            underRelativeDirs: Self.scannedDirectories, root: root, observable: observable
        )
        let foundKeys = Set(found.map(\.key))
        let stale = Self.allowlist.subtracting(foundKeys)
        #expect(
            stale.isEmpty,
            "These #4703 allowlist entries no longer violate the rule — the fix landed, so REMOVE them from the allowlist rather than leaving a stale pin: \(stale.sorted().joined(separator: "; "))"
        )
    }

    // MARK: - Positive pin: the six readers fixed in 48498334c stay optional

    struct FixedReader: Sendable {
        let file: String
        let line: Int
    }

    private static let fixedOptionalReaders: [FixedReader] = [
        FixedReader(file: "Views/Shell/Toolbar/StatusIslandToolbarItem.swift", line: 23),
        FixedReader(file: "Views/Shell/Toolbar/ActivityStatusToolbarItem.swift", line: 23),
        FixedReader(file: "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift", line: 84),
        FixedReader(file: "Views/Inspector/Artifacts/ArtifactEntityViews.swift", line: 31),
        FixedReader(file: "Views/Inspector/Artifacts/ArtifactEntityViews.swift", line: 206),
        FixedReader(file: "Views/Workflow/Inspector/WorkflowInspector.swift", line: 93),
    ]

    @Test("the six 48498334c WorkflowExecutionObserver readers stay optional", arguments: fixedOptionalReaders)
    func fixedReaderStaysOptional(reader: FixedReader) throws {
        let source = try AppSource.text(reader.file)
        let lines = source.components(separatedBy: "\n")
        let index = reader.line - 1
        guard lines.indices.contains(index) else {
            Issue.record("\(reader.file) has no line \(reader.line) any more — update this pin's line number.")
            return
        }
        let mintLine = lines[index]
        #expect(
            mintLine.contains("@Environment(WorkflowExecutionObserver.self)"),
            "\(reader.file):\(reader.line) was expected to mint @Environment(WorkflowExecutionObserver.self) (48498334c) — the line drifted, update this pin."
        )
        let declLine = mintLine.contains("var ") ? mintLine
            : (lines.indices.contains(index + 1) ? lines[index + 1] : "")
        #expect(
            declLine.contains("?"),
            "\(reader.file):\(reader.line) regressed to a non-optional WorkflowExecutionObserver read — 48498334c (#4703) required `: WorkflowExecutionObserver?` here."
        )
    }
}
