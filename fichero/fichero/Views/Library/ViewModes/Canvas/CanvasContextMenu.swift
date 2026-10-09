import SwiftUI

// MARK: - The canvas's context menu, 2D and 3D, every host (#5632, `library.canvas.context-menus`)

/// What a right-click on the canvas offers, as data: the canvas's own verbs on a card and on the
/// empty board. A card's DOCUMENT verbs (Open, Group, Run Workflow…, Move to Trash, …) are not
/// listed here: they come from the host's one document menu, the same menu every Library mode and
/// the sidebar show, so the canvas has no actions of its own for documents.
enum CanvasMenuItem: String, CaseIterable, Identifiable {
    /// Fill the view with the card; again to come back (the double-click's touch-reachable twin).
    case zoomToCard
    /// A new note at the centre of the view.
    case newNote
    /// Lay every card out in an order and save those places. The ONLY thing besides a drag that
    /// moves a card (`library.canvas.cards-move-only-when-asked`).
    case arrange
    /// Frame the whole board (⌘=).
    case zoomToFit
    /// The zoom a board opens at when it is the size of the view.
    case actualSize

    var id: String { rawValue }

    var title: String {
        switch self {
        case .zoomToCard: "Zoom to Card"
        case .newNote: "New Note"
        case .arrange: "Arrange By"
        case .zoomToFit: "Zoom to Fit"
        case .actualSize: "Actual Size"
        }
    }

    var systemImage: String {
        switch self {
        case .zoomToCard: "arrow.up.left.and.arrow.down.right"
        case .newNote: "note.text.badge.plus"
        case .arrange: "square.grid.3x3"
        case .zoomToFit: "arrow.up.left.and.down.right.magnifyingglass"
        case .actualSize: "1.magnifyingglass"
        }
    }
}

enum CanvasMenu {
    /// The canvas's own items for a right-click on a card (`onCard`) or on the board.
    static func items(onCard: Bool) -> [CanvasMenuItem] {
        onCard ? [.zoomToCard] : [.newNote, .arrange, .zoomToFit, .actualSize]
    }

    /// The orders Arrange offers: every arrangement that lays cards out. Free lays nothing out.
    static var arrangements: [CanvasArrangement] {
        CanvasArrangement.allCases.filter { $0 != .free }
    }
}

/// The menu itself, shared by the 2D canvas and the 3D space. `perform` runs a canvas verb;
/// `documentMenu` is the host's document menu for the card's selection (nil: the host offers none).
struct CanvasContextMenu: View {
    let onCard: Bool
    let perform: (CanvasMenuItem) -> Void
    let arrange: (CanvasArrangement) -> Void
    var documentMenu: (() -> AnyView)?

    var body: some View {
        ForEach(CanvasMenu.items(onCard: onCard)) { item in
            if item == .arrange {
                Menu {
                    ForEach(CanvasMenu.arrangements) { arrangement in
                        Button {
                            arrange(arrangement)
                        } label: {
                            Label(arrangement.label, systemImage: arrangement.icon)
                        }
                    }
                } label: {
                    Label(item.title, systemImage: item.systemImage)
                }
            } else {
                Button {
                    perform(item)
                } label: {
                    Label(item.title, systemImage: item.systemImage)
                }
            }
        }
        if onCard, let documentMenu {
            Divider()
            documentMenu()
        }
    }
}
