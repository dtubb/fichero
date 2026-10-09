//
//  CanvasContextMenuTests.swift
//  FicheroTests
//
//  #5632 (`library.canvas.context-menus`): a right-click on the canvas, 2D and 3D, in every host,
//  opens a menu. On a card: the canvas's card verbs, then the host's ONE document menu (the menu
//  every Library mode shows). On the board: New Note, Arrange By, Zoom to Fit, Actual Size.
//  The canvas spells no document verb itself (`LibraryMenuParityTests` pins that half).
//

@testable import Fichero
import Testing

@MainActor
@Suite("Canvas: context menus (#5632)")
struct CanvasContextMenuTests {

    // WHY: the issue's two menus. A card's own verb is Zoom to Card (the double-click's
    // touch-reachable twin); its document verbs come from the host.
    @Test("a card's menu and the board's menu offer the canvas's verbs")
    func items() {
        #expect(CanvasMenu.items(onCard: true) == [.zoomToCard, .makeBigger, .makeSmaller, .normalSize])
        #expect(CanvasMenu.items(onCard: false) == [.newNote, .arrange, .zoomToFit, .actualSize])
    }

    // WHY: Arrange is the explicit "move my cards" act (#5629); Free lays nothing out, so a menu
    // offering it would be an item that does nothing.
    @Test("Arrange By offers every order that lays cards out, and not Free")
    func arrangements() {
        #expect(CanvasMenu.arrangements == CanvasArrangement.allCases.filter { $0 != .free })
        #expect(!CanvasMenu.arrangements.contains(.free))
        #expect(CanvasMenu.arrangements.contains(.asFiled))
    }

    // WHY: every item has a title and a symbol, so no row of the menu is blank.
    @Test("every item is labelled")
    func labelled() {
        for item in CanvasMenuItem.allCases {
            #expect(!item.title.isEmpty)
            #expect(!item.systemImage.isEmpty)
        }
    }
}
