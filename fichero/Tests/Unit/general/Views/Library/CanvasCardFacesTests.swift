import CoreGraphics
@testable import Fichero
import Foundation
import Testing

/// The canvas's folder and note cards, and its camera (Daniel, 2026-10-11): folders and notes drew as plain blue
/// tiles with nothing in them, and a folder of 92 pages showed nothing but two stray dots.
@MainActor
struct CanvasCardFacesTests {
    private let folder = Document(id: "caciques", docType: .folder, name: "CACIQUES", childCount: 92)
    private let page = Document(id: "p1", parentId: "box", docType: .page, name: "f. 1r", sequence: 1)
    private let note = Document(id: "n1", fileType: .text, name: "Reading notes",
                                pageContent: "Juan de Mosquera appears as vecino of Popayán.")
    private let workflow = Document(id: "w1", name: "Transcribe (Kraken)", prototypeKey: "workflow")
    private let group = Document(id: "g1", docType: .group, name: "Letter of 1740")

    // MARK: Step 1: the kind goes through the projector

    @Test("a folder and a note are their own kinds on the board; only a page fetches a picture")
    func kindsThroughTheProjector() {
        let board = CanvasBoard.of(documents: [folder, page, note, workflow, group])
        let byId = Dictionary(uniqueKeysWithValues: board.projection.nodes.map { ($0.id, $0) })
        #expect(byId["doc:caciques"]?.nodeType == .folder)
        #expect(byId["doc:caciques"]?.sourceId == nil, "a folder never fetches a thumbnail")
        #expect(byId["doc:n1"]?.nodeType == .note && byId["doc:n1"]?.sourceId == nil)
        #expect(byId["doc:w1"]?.nodeType == .note, "a workflow is drawn as a card of its own, not a page")
        #expect(byId["doc:p1"]?.nodeType == .source && byId["doc:p1"]?.sourceId == "p1")
        #expect(byId["doc:g1"]?.nodeType == .source, "a group stays a frame of its pages (#5570)")
        #expect(SpaceTheme.platformColor(for: .folder) != SpaceTheme.platformColor(for: .source), "not plain blue")
    }

    @Test("a folder's card says what it holds; a note's card its text; a page has no face")
    func facesSayWhatTheyHold() throws {
        let inside = (1...7).map { Document(id: "c\($0)", parentId: "caciques", docType: .page, name: "f. \($0)r") }
        let board = CanvasBoard.of(documents: [folder, page, note, workflow], contents: ["caciques": inside])
        let folderFace = try #require(board.faces["doc:caciques"])
        guard case .folder(let count, let names, let pictureIds) = folderFace.content else {
            Issue.record("a folder's face lists its contents"); return
        }
        #expect(count == 7)
        #expect(names.count == CanvasCardFace.namesShown && names.first == "f. 1r")
        #expect(pictureIds == ["c1", "c2", "c3", "c4"], "up to four pictures")
        #expect(folderFace.tint == .folder)
        #expect(board.faces["doc:n1"]?.content == .note(text: "Juan de Mosquera appears as vecino of Popayán."))
        #expect(board.faces["doc:w1"]?.tint == .workflow)
        #expect(board.faces["doc:p1"] == nil)
        // Without its contents read, a folder's card still says how many it holds.
        let unread = CanvasBoard.of(documents: [folder]).faces["doc:caciques"]
        #expect(unread?.content == .folder(count: 92, names: [], pictureIds: []))
    }

    // MARK: Step 2: the face is drawn

    @Test("a folder's card image is drawn and is not blank")
    func folderFaceIsNotBlank() throws {
        let face = CanvasCardFace(title: "CACIQUES",
                                  content: .folder(count: 92, names: ["f. 1r", "f. 1v"], pictureIds: []),
                                  tint: .folder)
        let image = try #require(face.image())
        #expect(image.width == 480 && image.height == 600, "240 × 300 points at twice the scale")
        #expect(Self.distinctColours(in: image) > 2, "the colour, the name and the contents, not one flat fill")
    }

    // MARK: Step 3: the camera fits the cards

    @Test("the camera frames every card, for 1, 12 and 92 cards")
    func fitFramesEveryCard() throws {
        let viewport = CGSize(width: 640, height: 600)
        for count in [1, 12, 92] {
            let cards = Self.grid(count)
            let pose = try #require(CanvasCameraFit.fit(cards, viewport: viewport, margin: 0.5))
            let halfHeight = pose.orthoScale, halfWidth = pose.orthoScale * Float(viewport.width / viewport.height)
            for card in cards {
                #expect(card.center.x - card.size.x / 2 >= pose.center.x - halfWidth - 0.0001, "\(count): left")
                #expect(card.center.x + card.size.x / 2 <= pose.center.x + halfWidth + 0.0001, "\(count): right")
                #expect(card.center.y - card.size.y / 2 >= pose.center.y - halfHeight - 0.0001, "\(count): bottom")
                #expect(card.center.y + card.size.y / 2 <= pose.center.y + halfHeight + 0.0001, "\(count): top")
            }
            #expect(CanvasCameraFit.shows(pose, cards, viewport: viewport))
        }
        #expect(CanvasCameraFit.fit([], viewport: viewport, margin: 0.5) == nil)
    }

    @Test("a remembered camera that frames nothing, or leaves the board as specks, is not restored")
    func strayCameraIsReplaced() {
        let viewport = CGSize(width: 640, height: 600)
        let cards = Self.grid(92)
        #expect(!CanvasCameraFit.shows(.init(center: SIMD2(500, 500), orthoScale: 2), cards, viewport: viewport),
                "looking away from the board")
        #expect(!CanvasCameraFit.shows(.init(center: SIMD2(5, -5), orthoScale: 2000), cards, viewport: viewport),
                "the board as two stray dots")
    }

    /// Cards laid out as the canvas's grid does: ten columns of 1 × 0.75, a cell of 1.2 × 0.95.
    static func grid(_ count: Int) -> [CanvasCameraFit.Card] {
        (0..<count).map { index in
            CanvasCameraFit.Card(center: SIMD2(Float(index % 10) * 1.2, -Float(index / 10) * 0.95),
                                 size: SIMD2(1, 0.75))
        }
    }

    /// How many different colours an image has (sampled), to tell a drawn card from a flat fill.
    static func distinctColours(in image: CGImage) -> Int {
        let width = image.width, height = image.height
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        guard let context = CGContext(data: &pixels, width: width, height: height, bitsPerComponent: 8,
                                      bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return 0 }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        var colours = Set<UInt32>()
        for index in stride(from: 0, to: pixels.count, by: 4 * 97) {
            colours.insert(UInt32(pixels[index]) << 16 | UInt32(pixels[index + 1]) << 8 | UInt32(pixels[index + 2]))
        }
        return colours.count
    }
}
