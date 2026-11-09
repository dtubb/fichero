import FicheroAPIClient
import Foundation

/// The ONE mapping of a page's segment onto the picture shown (`prep.preview-draws-segments-on-the-selected-rendition`, #6420):
/// the engine's `frame_bbox` for an edited image or a rendition, the photograph's `bbox` otherwise, and no box where the
/// lines' place on the picture is not known. Compare reads it; the Preview's overlay is to read it, in place of its own
/// match-or-skip matrix. Pure: no view, no network.
enum SegmentOnRendition {
    /// A line's box and the size of the pixels it is in, for the picture shown. The picture is the page's saved edits when it has
    /// any (`frame.read_from == "edited"`), else the photograph. On an edited page the boxes are `frame_bbox` in the edited
    /// image's size, and when the lines' place on it is not known (`followed` false) no box is drawn; otherwise the line's `bbox`
    /// in the photograph's pixels.
    static func drawnBox(boxes: (bbox: [Double]?, frame: [Double]?), readFrom: String?, followed: Bool,
                         frameSize: (width: Int, height: Int)?, photograph: (width: Int, height: Int)?)
        -> (box: [Double], image: (width: Int, height: Int))? {
        if readFrom == "edited" {
            guard followed, let box = boxes.frame, let frameSize else { return nil }
            return (box, frameSize)
        }
        guard let bbox = boxes.bbox, let photograph else { return nil }
        return (bbox, photograph)
    }

    /// Said under the picture when the page has saved edits whose lines' place is not known: no box is drawn, and why.
    static func noBoxesNote(readFrom: String?, followed: Bool) -> String? {
        readFrom == "edited" && !followed
            ? "The lines' place on this edited page is not known, so no boxes are drawn." : nil
    }

    /// `drawnBox` over one of the engine's compare lines and its answer's frame.
    static func drawnBox(of line: Components.Schemas.CompareLine, frame: Components.Schemas.CompareFrame?,
                         photograph: (width: Int, height: Int)?) -> (box: [Double], image: (width: Int, height: Int))? {
        var size: (width: Int, height: Int)?
        if let width = frame?.imageWidth, let height = frame?.imageHeight { size = (width, height) }
        return drawnBox(boxes: (line.bbox, line.frameBbox), readFrom: frame?.readFrom.rawValue,
                        followed: frame?.followed ?? false, frameSize: size, photograph: photograph)
    }

    /// Select All (⌘A) over the Preview, as indices into the page's geometry. With the text tool armed every WORD (every box
    /// when none is a word); otherwise what the overlay is SHOWING, or every box when it shows none. Whether the geometry's
    /// frame is the picture's decides only what is DRAWN, never what is selected: on a rendition that does not match, the
    /// page's segments are all selected (#6448; the old rule read the frame-matched list, which is empty there).
    static func selectAllIndices(levels: [String], shown: [Int], frameMatches: Bool, isTextTool: Bool) -> [Int] {
        let every = Array(levels.indices)
        if isTextTool {
            let words = every.filter { levels[$0] == "word" }
            return words.isEmpty ? every : words
        }
        return frameMatches && !shown.isEmpty ? shown : every
    }
}
