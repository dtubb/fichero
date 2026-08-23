import SwiftUI

// MARK: - The Reader's surface inventory (R3, 2026-08-23)

/// Every reader surface that is actually BUILT, as one list.
///
/// R3 folds the reader's tabs into the pane head's two-level selector: the pane
/// KIND says Reader, the LENS says which of its surfaces you are looking at.
/// This enum is that lens list, and it is deliberately an INVENTORY — a row
/// here means the surface exists and renders. Daniel, 2026-08-23: the reader
/// "lost some things like node graph and maps — they're in the menu bar",
/// which is exactly the defect this fixes. Graph and Map were built and
/// reachable only through the View menu's Add View section.
///
/// **Translation is absent because it does not exist.** A lens that goes
/// nowhere is the menu lying (dead-simple-UX: features are ON or OFF), so new
/// lenses join when their surfaces land, not before.
///
/// **Where each lens lives** — the file layout tells the same story:
/// - `page`, `notes` → `Views/Reader/Page/` (`ReadingPaneView+Tabs`)
/// - `statements` → `Views/Reader/Knowledge/DocumentKGWebPane`
///   (WebKit, over the engine's assembled document view)
/// - `entities`, `claims`, `graph`, `timeline`, `map` →
///   `Views/Reader/Knowledge/DocumentKGSurface` native sub-modes
///
/// The two existing enums stay as the IMPLEMENTATION vocabulary: a lens maps to
/// a `ReaderTab` plus, for the knowledge surfaces, a `KGSurfaceTab`. One
/// user-facing list, two internal switches, no third source of truth.
enum ReaderLens: String, CaseIterable, Identifiable, Sendable {
    /// The multi-page WebKit transcript — the whole point of the Reader.
    /// There is NO separate "Transcript" lens (Daniel, 2026-08-23: "Transcript
    /// vs Page — what's the difference?" — there was none; both rendered the
    /// same WebKit transcript, and the Transcript row even landed on Entities
    /// because the knowledge surface clamps `.transcript` as stale).
    case page
    /// `KGSurfaceTab.digest`'s user-facing name: the SVO statements (#3765).
    case statements
    case entities
    case claims
    case graph
    case timeline
    case map
    case notes

    var id: String { rawValue }

    var title: String {
        switch self {
        case .page: "Page"
        case .statements: "Statements"
        case .entities: "Entities"
        case .claims: "Claims"
        case .graph: "Node Graph"
        case .timeline: "Timeline"
        case .map: "Map"
        case .notes: "Notes"
        }
    }

    var icon: String {
        switch self {
        case .page: "doc.text.image"
        case .statements: "text.quote"
        case .entities: "circle.grid.2x2"
        case .claims: "quote.bubble"
        case .graph: "point.3.connected.trianglepath.dotted"
        case .timeline: "calendar.badge.clock"
        case .map: "map"
        case .notes: "note.text"
        }
    }

    /// Which top-level reader tab hosts this lens.
    var tab: ReaderTab {
        switch self {
        case .page: .page
        case .notes: .notes
        case .statements, .entities, .claims, .graph, .timeline, .map: .knowledge
        }
    }

    /// The knowledge sub-mode this lens selects, or nil for the lenses that are
    /// a whole tab on their own.
    var representation: KGSurfaceTab? {
        switch self {
        case .page, .notes: nil
        case .statements: .digest
        case .entities: .entities
        case .claims: .claims
        case .graph: .graph
        case .timeline: .timeline
        case .map: .map
        }
    }

    /// The lens showing this tab + sub-mode — the inverse, so restoring saved
    /// state or a menu-bar selection lands on the same row the head shows.
    static func lens(for tab: ReaderTab, representation: KGSurfaceTab) -> ReaderLens {
        switch tab {
        case .page: .page
        case .notes: .notes
        case .knowledge: allCases.first { $0.representation == representation } ?? .entities
        }
    }
}
