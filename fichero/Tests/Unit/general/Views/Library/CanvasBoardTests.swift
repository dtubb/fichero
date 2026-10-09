//
//  CanvasBoardTests.swift
//  FicheroTests
//
//  `library.canvas.one-canvas-everywhere` (ruled 2026-10-09): the folder canvas in the Preview
//  and the Library's Canvas and Space are one canvas. Both hosts draw `CanvasSceneView` and build
//  its inputs with `CanvasBoard`. Before, each host built them its own way: the Preview passed no
//  drop-into containers, so a card could be dropped into a subfolder in the Library's canvas and
//  not in the Preview's.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("Canvas: one board for every host")
struct CanvasBoardTests {

    private func folderContents() -> [Document] {
        [
            Document(id: "p1", parentId: "f", docType: .file, fileType: .image, name: "page 1", sortOrder: 0),
            Document(id: "g", parentId: "f", docType: .group, name: "opening"),
            Document(id: "sub", parentId: "f", docType: .folder, name: "letters"),
            Document(id: "p2", parentId: "f", docType: .file, fileType: .image, name: "page 2", sortOrder: 1)
        ]
    }

    // WHY: the cards are the documents, one each, under the node ids every canvas reads and writes
    // layout rows under; a group is a frame (#5570) and a folder is a drop-into target (#3086).
    @Test("a folder's board: a card per document, its groups and its containers")
    func board() {
        let board = CanvasBoard.of(documents: folderContents())
        #expect(Set(board.projection.nodes.map(\.id)) == ["doc:p1", "doc:g", "doc:sub", "doc:p2"])
        #expect(board.groupNodeIds == ["doc:g"])
        #expect(board.containerIds == ["doc:sub"])
    }

    // WHY: the Preview's folder canvas and the Library's canvas over the same folder build the same
    // board, so the same documents give the same cards in both; the Library's whole-library board
    // adds its entities, and only them.
    @Test("the same documents give the same board in either host")
    func sameDocumentsSameBoard() {
        let preview = CanvasBoard.of(documents: folderContents())
        let library = CanvasBoard.of(documents: folderContents(), entities: [])
        #expect(preview == library)

        let withEntity = CanvasBoard.of(
            documents: folderContents(),
            entities: [SpatialLibraryInput.Entity(id: "e1", canonicalName: "Marshall", entityType: "person")]
        )
        #expect(withEntity.groupNodeIds == preview.groupNodeIds)
        #expect(withEntity.containerIds == preview.containerIds)
        #expect(Set(preview.projection.nodes.map(\.id)).isSubset(of: Set(withEntity.projection.nodes.map(\.id))))
    }

    // WHY: colouring off leaves every card its own colour, in both hosts.
    @Test("no colouring is neutral")
    func noColouring() {
        #expect(CanvasBoard.tint(of: folderContents(), by: .off) == .neutral)
    }
}
