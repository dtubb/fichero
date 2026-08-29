import Foundation
import SwiftUI

/// Xcode-style center status island (#4036 follow-up): the MESSAGE area that
/// says what the app is doing (starting the engine, connecting to libraries,
/// importing, running workflows, errors, the selection) beside the window
/// title.
///
/// The engine and activity buttons are NOT in here (Daniel, 2026-08-23: "the
/// island must separate from server status and activity — they're all in one
/// right now"): `EngineStatusToolbarItem` and `ActivityStatusToolbarItem` are
/// their own toolbar items, so each gets its own Liquid Glass section and its
/// own popover.
///
/// Hosted by ONE unconditionally-declared `ToolbarItem` (#3163 guard: only
/// CONTENT varies with state, the item itself never appears/disappears).
struct StatusIslandToolbarItem: View {
    @Environment(AppState.self) private var appState
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(ActivityStore.self) private var activityStore
    /// Optional: the island renders before any library is open (#4203).
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?

    let isImporting: Bool
    let importProgress: String?
    let libraryId: UUID
    let libraryName: String
    /// Photos-style selection indicator (#29, Daniel #138): the count being
    /// built, the single item's display name and glyph, and the noun a
    /// multi-selection counts in ("2 images selected" — no totals, Daniel,
    /// bedtime 2026-08-23). One value, so the island and `resolve` cannot
    /// take different slices of the same selection.
    let selection: StatusIslandSelection
    @Binding var importError: String?

    var body: some View {
        HStack(spacing: 8) {
            // A live folder import replaces the generic message with real
            // numbers and a Cancel — the island is where the user looks first,
            // and "importing…" with no count is what #4203 is about.
            if let library = libraryManager?.importingLibrary,
               let ingest = library.importService.activeIngest {
                IngestProgressView(
                    status: ingest,
                    libraryName: library.displayName,
                    isCompact: true,
                    onCancel: { Task { await library.importService.cancelActiveIngest() } }
                )
            } else if let library = libraryManager?.importingLibrary {
                // #4235: importing, but the engine has no task yet — staging,
                // the folder grant and the create call all precede it. Show
                // that the drop registered rather than nothing at all. No
                // Cancel: there is no task to cancel until the engine has one.
                ProgressView()
                    .controlSize(.small)
                // "Importing to X…", not "Preparing import to X…": this is
                // shown for the whole import, not just the staging phase it was
                // named after. Same correction as the library pane's
                // placeholder — the two must not drift apart, since a user sees
                // both at once (2026-08-04).
                Text("Importing to \(library.displayName)…")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                message
            }
        }
        // No painted background (#4360). On macOS 26 the toolbar itself wraps
        // this principal item in the system's Liquid Glass; the old
        // `.quaternary.opacity(0.5)` fill sat ON TOP of that glass as an
        // opaque plate — white-ish in dark appearance, where `.quaternary`
        // resolves from a white primary. Native chrome means letting NSToolbar
        // own the material; the island supplies content only.
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Status")
    }

    private var message: some View {
        let status = StatusIslandMessage.resolve(
            enginePhase: appState.engine.phase,
            // The MAPPED short title, never the engine's raw diagnosis (#4366):
            // the debug-external diagnosis is a multi-line
            // `PYTHONPATH=src python -m fichero_server.api` invocation, and the
            // island rendered it truncated to a fragment of a shell command.
            // Detail belongs in the popover; the line carries the short form.
            engineStatusTitle: ConnectionPresentation.status(
                phase: appState.engine.phase,
                ownership: ConnectionPresentation.EngineOwnership.current(),
                accessError: appState.backendAccessError,
                authBroken: appState.authBroken
            ).shortTitle,
            importError: importError,
            isImporting: isImporting,
            importProgress: importProgress,
            backendWorkLabel: activityStore.backendWork.map(Self.label(for:)),
            runningWorkflows: executionObserver.activeExecutions.count,
            selection: selection
        )
        // Icon + standard body type (Daniel, bedtime 2026-08-23): the island
        // wears the selection's glyph and the system's standard size; a quiet
        // app shows NOTHING rather than "Ready".
        return HStack(spacing: 5) {
            if !status.text.isEmpty, let icon = selection.icon, selection.count >= 1, !status.isError {
                Image(systemName: icon)
                    .foregroundStyle(Color.accentColor)
            }
            Text(status.text)
                .font(.body)
                .foregroundStyle(status.isError ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
                .lineLimit(1)
                .truncationMode(.tail)
        }
            // The width `StatusIslandMessage.budget` was derived from (#4366).
            // Named rather than inlined so the two cannot drift: widen the
            // island and the budget test tells you to re-derive the character
            // count. `truncationMode` stays as a backstop for a pathological
            // glyph run — it is not the length policy.
            .frame(minWidth: 40, maxWidth: StatusIslandMessage.declaredMaxWidth)
            // Breathing room inside the glass capsule (Daniel, 2026-08-29:
            // "the left and right margin ... is too narrow") — the selection
            // name was touching the capsule on both sides.
            .padding(.horizontal, 8)
    }

    private static func label(for work: BackendWorkStatus) -> String {
        let name = work.taskName.isEmpty ? "Backend work" : work.taskName
        return work.total > 0 ? "\(name) — \(work.displayPercent)%" : name
    }
}

/// The one line the status island shows, chosen by urgency.
///
/// Pure and static on purpose: the precedence between "the engine can't
/// connect" and "an import failed" and "three workflows are running" is real
/// logic with real branches, and keeping it out of the view body is what makes
/// it testable without an engine, a store, or a rendered environment (#4036).
/// The selection as the island renders it: the count being built, the single
/// item's display name and glyph, the noun a multi-selection counts in. One
/// value type instead of four loose parameters (the swiftlint parameter-count
/// guard is right: four siblings travelling separately WILL drift).
struct StatusIslandSelection: Equatable {
    var count = 0
    var label: String?
    var icon: String?
    var noun = "items"
}

struct StatusIslandMessage: Equatable {
    let text: String
    let isError: Bool

    /// Characters that fit the island's line. One number, shared with
    /// `ConnectionPresentation` so the engine's short titles and the island's
    /// own strings are held to the same contract (#4366).
    static var budget: Int { ConnectionPresentation.islandBudget }

    /// The island's declared max width, in points. `islandBudget` was derived
    /// from THIS number; the test asserts the view still declares it, so
    /// widening the island forces the budget to be re-derived rather than
    /// silently drifting out of date.
    static let declaredMaxWidth: CGFloat = 260

    /// Every string the APP itself authors for the island.
    ///
    /// The table exists so a test can hold all of it to `budget` at once — the
    /// point of #4366 is that a new message which is too long fails a test
    /// rather than quietly truncating in the toolbar. Strings that come from
    /// OUTSIDE the app (a backend task name, an import error, an import
    /// progress line) are not in here; they cannot be written short in advance,
    /// so they go through `shortForm(_:)` instead.
    static let authoredMessages: [String] = [
        "Importing…",
        "Running 1 workflow…",
        "Running 99 workflows…",
        "9,999 documents selected"
    ]

    /// The short form of a string the app did not author.
    ///
    /// NOT a silent truncation: it is a named, tested seam that exists because
    /// a backend task name or an OS error string has no length contract, and
    /// the alternative — letting SwiftUI clip it at render time — is the bug.
    /// Clips on a word boundary where one is available so the result reads as
    /// a phrase rather than a severed word, and the full text stays where it
    /// already was (the activity popover, the import surface).
    ///
    /// A string already within budget is returned untouched, so this can never
    /// shorten something that did not need it.
    static func shortForm(_ text: String) -> String {
        // Flatten first: the island is ONE line, and a multi-line payload — the
        // debug-external engine diagnosis is three lines with a shell command in
        // the middle — must not arrive with hard returns in it. Collapsing every
        // whitespace run to a single space is what makes the length below a
        // meaningful measure of what will actually be drawn.
        let flattened = text
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        guard flattened.count > budget else { return flattened }
        // Leave room for the ellipsis so the RESULT is within budget, not the
        // part before it.
        let room = budget - 1
        let clipped = flattened.prefix(room)
        if let lastSpace = clipped.lastIndex(of: " ") {
            let words = clipped[..<lastSpace].trimmingCharacters(in: .whitespaces)
            // Only prefer the word boundary when it leaves a usable phrase; a
            // single very long word would otherwise collapse to just "…".
            if words.count >= room / 2 {
                return words + "…"
            }
        }
        return String(clipped) + "…"
    }

    /// Highest-urgency source first: engine failure → engine booting → import
    /// error → import → engine background work → workflows → idle. Errors
    /// outrank progress because a stalled connection explains why the progress
    /// stopped; engine state outranks import state because an import cannot
    /// proceed without the engine at all.
    /// - Parameter engineStatusTitle: the SHORT title from
    ///   `ConnectionPresentation.status(…)` — the same words the engine popover
    ///   puts at the top of the same failure. Never a raw diagnosis or a
    ///   transport error string (#4366/#4269/#4380).
    static func resolve(
        enginePhase: EngineSession.Phase,
        engineStatusTitle: String,
        importError: String?,
        isImporting: Bool,
        importProgress: String?,
        backendWorkLabel: String?,
        runningWorkflows: Int,
        selection: StatusIslandSelection = .init()
    ) -> StatusIslandMessage {
        switch enginePhase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return .init(text: engineStatusTitle, isError: true)
        case .starting:
            return .init(text: engineStatusTitle, isError: false)
        case .setupNeeded, .ready:
            break
        }
        // The three strings the app does NOT author. An OS error, a dropped
        // folder's progress line and a backend task name all arrive with no
        // length contract, so they are shortened at this ONE seam rather than
        // clipped by the renderer (#4366). Everything below this point is
        // app-authored and short by construction.
        if let importError { return .init(text: shortForm(importError), isError: true) }
        if isImporting { return .init(text: shortForm(importProgress ?? "Importing…"), isError: false) }
        // LIVE WORK outranks the selection (Ann, 2026-08-24: she ran a
        // workflow on 98 files and the island kept saying "98 selected" — "it
        // should say working on processing… it's not clear to her that it's
        // working"). The selection is usually the very thing being processed,
        // so echoing its count during a run reads as "nothing happened".
        if let backendWorkLabel { return .init(text: shortForm(backendWorkLabel), isError: false) }
        if runningWorkflows > 0 {
            let text = runningWorkflows == 1
                ? "Running 1 workflow…"
                : "Running \(runningWorkflows) workflows…"
            return .init(text: text, isError: false)
        }
        // Photos grammar (#29/#138): a multi-selection in progress is what the
        // user is actively doing when nothing is running.
        if selection.count > 1 {
            // "2 images selected" (Daniel, bedtime 2026-08-23) — the noun,
            // never a total.
            return .init(text: "\(selection.count.formatted()) \(selection.noun) selected", isError: false)
        }
        // ONE selection: the island names the ITEM (Daniel, 2026-08-23) —
        // what is selected, not which view shows it.
        if selection.count == 1, let label = selection.label, !label.isEmpty {
            return .init(text: shortForm(label), isError: false)
        }
        // Quiet idle shows NOTHING (Daniel: "it said ready on launch,
        // don't need that").
        return .init(text: "", isError: false)
    }
}
