import FicheroAPIClient
import Observation
import SwiftUI

//  Extracted for file_length (#5113) with the checklist from that issue: path asserted free,
//  cut above the declaration's attributes and doc comment, no conditional-compilation blocks,
//  ZERO file-scope `private` declarations to strand (every `private` here is a member and
//  travels with its type), imports copied from the source verbatim.

enum KGGraphRendererFramework: String {
    case cytoscapeWebKit = "cytoscape-webkit"

    static let selected: KGGraphRendererFramework = .cytoscapeWebKit

    var displayName: String {
        switch self {
        case .cytoscapeWebKit:
            return "Cytoscape.js (WebKit)"
        }
    }
}

@MainActor
@Observable
final class DocumentScrollSyncState {
    enum Pane {
        case pdf
        case web
    }

    private var drivingPane: Pane?
    private var releaseTask: Task<Void, Never>?

    func beginDriving(_ pane: Pane) -> Bool {
        guard drivingPane == nil || drivingPane == pane else { return false }
        drivingPane = pane
        releaseTask?.cancel()
        releaseTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(50))
            if self?.drivingPane == pane {
                self?.drivingPane = nil
            }
        }
        return true
    }

    func isDriving(_ pane: Pane) -> Bool {
        drivingPane == pane
    }
}

/// The views the knowledge surface can show. The first three raw values match
/// the tab ids the in-page JS (`document_view.html`) expects.
enum KGSurfaceTab: String, CaseIterable, Identifiable {
    case transcript
    /// Raw value stays "digest" — it is the WIRE CONTRACT with document_view.html
    /// (`data-tab="digest"`, and the literal tab list in its JS). The engine template
    /// is codex's lane, so the USER-FACING name changes here and the wire does not.
    /// What it actually shows: the SVO statements about each entity (#3765).
    case digest
    case graph
    case claims
    case timeline
    case map
    case entities
    /// The document's automatic see-also (#4120) — shared entities and
    /// embedding neighbours. It was an INSPECTOR tab only; Daniel, 2026-09-04:
    /// related documents "should be a reader option". It reads the same
    /// endpoint through the same view, so the two surfaces cannot drift.
    case related

    var id: String { rawValue }

    /// Human-readable label shown on the native toolbar button.
    var title: String {
        switch self {
        case .transcript: return "Transcript"
        case .digest: return "Statements"
        case .graph: return "Graph"
        case .claims: return "Claims"
        case .timeline: return "Timeline"
        case .map: return "Map"
        case .entities: return "Entities"
        case .related: return "Related"
        }
    }

    /// SF Symbol mirroring the inspector tab-bar visual language.
    var icon: String {
        switch self {
        case .transcript: return "doc.text"
        case .digest: return "list.bullet.indent"
        case .graph: return "point.3.connected.trianglepath.dotted"
        case .claims: return "quote.bubble"
        case .timeline: return "calendar.badge.clock"
        case .map: return "map"
        case .entities: return "circle.grid.2x2"
        case .related: return "doc.on.doc"
        }
    }

    /// Tooltip copy: what the view shows and how to use it. (#1371)
    var helpText: String {
        switch self {
        case .transcript: return "Transcript — read the document's full text"
        case .digest: return "Statements — every subject-verb-object statement we know about this entity"
        case .graph:
            return "Graph — entities and their connections as a network "
            + "(\(KGGraphRendererFramework.selected.displayName))"
        case .claims: return "Claims — statements extracted from the document, grouped by source"
        case .timeline: return "Timeline — dated entities and events in chronological order"
        case .map: return "Map — entities laid out on a visual canvas"
        case .entities: return "Entities — the people, places, and things named in the document"
        case .related:
            return "Related — other documents sharing this one's entities, "
            + "or nearest by meaning"
        }
    }

    /// Number key for the View-menu "Add View" shortcut (⌃⌥⌘N). Mirrors the
    /// menu order; chosen to avoid the ⌘N library-layout and ⌃⌘N sidebar-mode
    /// shortcuts. (#2032)
    var representationShortcut: Character {
        switch self {
        case .transcript: return "1"
        case .digest: return "2"
        case .graph: return "3"
        case .claims: return "4"
        case .timeline: return "5"
        case .map: return "6"
        case .entities: return "7"
        case .related: return "8"
        }
    }

    /// True for tabs rendered inside the shared WKWebView (#1346). The KG
    /// visualizations (Entities, Claims, Graph, Timeline, Map) render natively
    /// via inspector / OntologyBrowser components; only the transcript and the
    /// digest summary remain WebKit HTML.
    var usesWebKit: Bool {
        switch self {
        case .transcript, .digest: return true
        case .claims, .entities, .graph, .timeline, .map, .related: return false
        }
    }
}

/// Equatable focused-value wrapper for the active document representation.
///
/// Publishing a raw `Binding<KGSurfaceTab>` via `focusedSceneValue` is a perf
/// footgun: a `Binding` is non-Equatable, so SwiftUI cannot dedupe it and every
/// `body` pass republishes a "new" focused value, causing per-frame
/// invalidation churn ("FocusedValue update tried to update multiple times per
/// frame"). This wrapper keys equality on the *value* (`current`) so the
/// focused value only changes when the active representation actually changes;
/// the `select` closure is excluded from equality (closures are non-Equatable).
/// (#2032)
struct DocumentRepresentationFocus: Equatable {
    let current: KGSurfaceTab
    let select: (KGSurfaceTab) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.current == rhs.current
    }
}
