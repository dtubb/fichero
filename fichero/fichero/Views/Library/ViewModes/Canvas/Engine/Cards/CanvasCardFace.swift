import CoreGraphics
import SwiftUI

/// What a folder's or a note's card shows on a canvas (Daniel, 2026-10-11): its own colour, its name, and what it
/// holds (the names inside, and up to four of their pictures) or, for a note, its text. A page's card shows the page
/// itself instead (its thumbnail), so it has no face.
struct CanvasCardFace: Equatable {
    enum Content: Equatable {
        /// A folder: how many items it holds, the first names, the ids of up to four items with a picture.
        case folder(count: Int, names: [String], pictureIds: [String])
        /// A note, a text file, or a workflow: its text.
        case note(text: String)
    }

    /// The card's own colour (`CanvasCardFace.Tint`).
    enum Tint: Equatable {
        case folder, workflow, note

        var color: Color {
            switch self {
            case .folder: Color(red: 0.62, green: 0.80, blue: 0.95)
            case .workflow: Color(red: 0.78, green: 0.66, blue: 0.93)
            case .note: Color(red: 0.99, green: 0.89, blue: 0.55)
            }
        }
    }

    let title: String
    let content: Content
    let tint: Tint

    /// How many names and pictures a folder's card shows.
    static let namesShown = 6
    static let picturesShown = 4

    /// The face for a document on a canvas, or nil for a page or file (which shows its picture). `contents` are the
    /// folder's own items, when the host has read them; without them a folder's card says how many it holds.
    static func of(_ document: Document, contents: [Document]? = nil) -> CanvasCardFace? {
        let title = DocumentTitle.displayName(for: document)
        // A group is a frame holding its pages (#5570), not a folder's card.
        if document.docType == .folder {
            let items = contents ?? []
            let pictures = items.filter { $0.docType == .page || $0.fileType == .image || $0.fileType == .pdf }
            return CanvasCardFace(
                title: title,
                content: .folder(count: contents?.count ?? document.childCount,
                                 names: items.prefix(namesShown).map { DocumentTitle.displayName(for: $0) },
                                 pictureIds: pictures.prefix(picturesShown).map(\.id)),
                tint: document.usesWorkflowTint ? .workflow : .folder
            )
        }
        if document.isWorkflowNode {
            return CanvasCardFace(title: title, content: .note(text: "Workflow"), tint: .workflow)
        }
        if document.fileType == .text {
            return CanvasCardFace(title: title, content: .note(text: document.pageContent ?? ""), tint: .note)
        }
        return nil
    }

    /// The node kind the canvas draws a document as: a folder's card, a note's, or a page's.
    static func kind(of document: Document) -> SpatialNodeType {
        if document.docType == .folder { return .folder }
        if document.isWorkflowNode || document.fileType == .text { return .note }
        return .source
    }

    /// The card's picture, drawn by SwiftUI (`ImageRenderer`) for the renderer's texture. `pictures` are the
    /// folder's items' thumbnails, by id, as far as they have loaded.
    @MainActor
    func image(pictures: [String: CGImage] = [:], size: CGSize = CGSize(width: 240, height: 300)) -> CGImage? {
        let renderer = ImageRenderer(content: CanvasCardFaceView(face: self, pictures: pictures)
            .frame(width: size.width, height: size.height))
        renderer.scale = 2
        return renderer.cgImage
    }
}

/// A folder's or a note's card, as drawn into its texture.
struct CanvasCardFaceView: View {
    let face: CanvasCardFace
    var pictures: [String: CGImage] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(face.title, systemImage: icon)
                .font(.headline)
                .lineLimit(2)
            switch face.content {
            case .folder(let count, let names, let pictureIds):
                let shown = pictureIds.compactMap { pictures[$0] }
                if !shown.isEmpty {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 4) {
                        ForEach(Array(shown.enumerated()), id: \.offset) { _, picture in
                            Image(decorative: picture, scale: 1)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(maxHeight: 70)
                        }
                    }
                }
                ForEach(names, id: \.self) { name in
                    Text(name).font(.caption).lineLimit(1)
                }
                Spacer(minLength: 0)
                Text(count == 1 ? "1 item" : "\(count) items")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            case .note(let text):
                Text(text)
                    .font(.callout)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Spacer(minLength: 0)
            }
        }
        .foregroundStyle(.black)
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(face.tint.color, in: RoundedRectangle(cornerRadius: 14))
    }

    private var icon: String {
        switch face.content {
        case .folder: face.tint == .workflow ? "folder.badge.gearshape" : "folder"
        case .note: face.tint == .workflow ? "point.3.connected.trianglepath.dotted" : "note.text"
        }
    }
}

#Preview("A folder's card and a note's") {
    HStack {
        CanvasCardFaceView(face: CanvasCardFace(
            title: "CACIQUES", content: .folder(count: 92, names: ["f. 1r", "f. 1v", "f. 2r"], pictureIds: []),
            tint: .folder))
        .frame(width: 240, height: 300)
        CanvasCardFaceView(face: CanvasCardFace(
            title: "Reading notes", content: .note(text: "Juan de Mosquera appears as vecino of Popayán."), tint: .note))
        .frame(width: 240, height: 300)
    }
    .padding()
}
