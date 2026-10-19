import CoreGraphics
import Foundation

/// What a Set Up stage's picture plays on (#5668, `source.onboard.stages.shows-what-it-does`): one page, its picture
/// and what was found on it, in the picture's own pixels. Either the person's own sample page with what the stage's try
/// made, or the example page shipped with the app. The stage views draw from this alone.
struct StageShowcase: Equatable {
    /// Where the page's picture comes from.
    enum Picture: Equatable {
        /// The example page, a JPEG in the app bundle (`Resources/StageShowcase`).
        case bundled(URL)
        /// A page of the project, by its document id (the project's storage draws it).
        case sample(pageId: String)
    }

    /// A stretch of one line's text: a name, a date, a match.
    struct Mark: Hashable, Decodable {
        let line: Int
        let start: Int
        let end: Int
        var kind: String?
        var value: String?
    }

    struct Line: Equatable {
        /// `[x, y, width, height]` in the picture's pixels; nil when only the text is known (a sample's reading).
        let box: CGRect?
        let baseline: [CGPoint]?
        let text: String
    }

    struct Region: Equatable {
        let kind: String
        let box: CGRect
    }

    struct Statement: Equatable {
        /// Where the statement's subject and object are on the page; nil on a sample's page (its words only).
        let subject: Mark?
        let object: Mark?
        let label: String
    }

    struct Expansion: Equatable {
        let line: Int
        let written: String
        let expanded: String
    }

    struct Cell: Equatable {
        let field: String
        let value: String
        /// Where on the page the value came from: a stretch of a line, or a box.
        let from: Mark?
        let box: CGRect?
    }

    let picture: Picture
    /// The picture's size in pixels, when known; boxes are drawn only then.
    let size: CGSize?
    let regions: [Region]
    let lines: [Line]
    let names: [Mark]
    let dates: [Mark]
    let statements: [Statement]
    let passage: [Int]
    let expansions: [Expansion]
    let translation: (line: Int, text: String)?
    let table: [Cell]
    let search: (query: String, matches: [Mark])?
    /// The example's credit, shown under it ("Example: BNE · DILE, CC BY-SA 4.0"); nil on the person's own page.
    let credit: String?
    let licenceURL: URL?
    /// The example's own page (#5803): the credit's first half links here, the licence's deed is `licenceURL`.
    let sourceURL: URL?

    static func == (lhs: StageShowcase, rhs: StageShowcase) -> Bool {
        // One comparison per line: a single chain of a dozen `&&` can outrun the type checker.
        guard lhs.picture == rhs.picture, lhs.size == rhs.size, lhs.regions == rhs.regions else { return false }
        guard lhs.lines == rhs.lines, lhs.names == rhs.names, lhs.dates == rhs.dates else { return false }
        guard lhs.statements == rhs.statements, lhs.passage == rhs.passage else { return false }
        guard lhs.expansions == rhs.expansions, lhs.table == rhs.table, lhs.credit == rhs.credit else { return false }
        let sameTranslation: Bool = lhs.translation?.line == rhs.translation?.line
            && lhs.translation?.text == rhs.translation?.text
        let sameSearch: Bool = lhs.search?.query == rhs.search?.query && lhs.search?.matches == rhs.search?.matches
        return sameTranslation && sameSearch
    }

    /// Whether the person's own page is shown (not the example).
    var isOwnPage: Bool {
        if case .sample = picture { return true }
        return false
    }

    /// The text of a mark, or nil when it points past its line.
    func text(of mark: Mark) -> String? {
        guard lines.indices.contains(mark.line) else { return nil }
        let characters = Array(lines[mark.line].text)
        guard mark.start >= 0, mark.end <= characters.count, mark.start < mark.end else { return nil }
        return String(characters[mark.start..<mark.end])
    }

    /// Where a mark sits on the picture: its share of its line's box, by characters (an estimate the pictures use
    /// to light a word; nil without a box).
    func box(of mark: Mark) -> CGRect? {
        guard lines.indices.contains(mark.line), let box = lines[mark.line].box else { return nil }
        let count = max(1, lines[mark.line].text.count)
        let left = box.minX + box.width * CGFloat(mark.start) / CGFloat(count)
        let right = box.minX + box.width * CGFloat(mark.end) / CGFloat(count)
        return CGRect(x: left, y: box.minY, width: max(4, right - left), height: box.height)
    }
}

// MARK: - The example page shipped with the app

/// The example page's file (`Resources/StageShowcase/<image>.json`): Diálogo de la Lengua, manuscript p. 18 (BNE,
/// public domain; transcription after DILE, CC BY-SA 4.0), with its licence and credit kept beside its data.
struct StageShowcaseExample: Decodable, Equatable {
    struct Line: Decodable, Equatable {
        let box: [Double]
        let baseline: [[Double]]
        let text: String
    }

    struct Region: Decodable, Equatable {
        let kind: String
        let box: [Double]
    }

    struct Statement: Decodable, Equatable {
        let subject: StageShowcase.Mark
        let object: StageShowcase.Mark
        let label: String
    }

    struct Expansion: Decodable, Equatable {
        let line: Int
        let written: String
        let expanded: String
    }

    struct Translation: Decodable, Equatable {
        let line: Int
        let text: String
    }

    struct Cell: Decodable, Equatable {
        let field: String
        let value: String
        let from: StageShowcase.Mark?
        let box: [Double]?
    }

    struct Search: Decodable, Equatable {
        let query: String
        let matches: [StageShowcase.Mark]
    }

    struct Passage: Decodable, Equatable {
        let lines: [Int]
    }

    let image: String
    let width: Double
    let height: Double
    let title: String
    let credit: String
    let licence: String
    let source: String
    let shortCredit: String
    let licenceUrl: String
    let regions: [Region]
    let lines: [Line]
    let names: [StageShowcase.Mark]
    let dates: [StageShowcase.Mark]
    let statements: [Statement]
    let passage: Passage
    let normalise: [Expansion]
    let translation: Translation
    let table: [Cell]
    let search: Search

    static let resourceName = "dialogo-lengua-p18"

    static func decode(_ data: Data) throws -> StageShowcaseExample {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(StageShowcaseExample.self, from: data)
    }

    /// The example from the app bundle; nil if it is missing (it ships with the app).
    static func bundled(in bundle: Bundle = .main) -> (example: StageShowcaseExample, imageURL: URL)? {
        guard let json = bundle.url(forResource: resourceName, withExtension: "json"),
              let image = bundle.url(forResource: resourceName, withExtension: "jpg"),
              let data = try? Data(contentsOf: json),
              let example = try? decode(data) else { return nil }
        return (example, image)
    }

    /// Every box and baseline lies on the picture.
    var fitsImage: Bool {
        let frame = CGRect(x: 0, y: 0, width: width, height: height)
        var boxes: [[Double]] = regions.map(\.box)
        boxes += lines.map(\.box)
        boxes += table.compactMap(\.box)
        for box in boxes where box.count != 4 || !frame.contains(Self.rect(box)) { return false }
        for line in lines {
            for point in line.baseline where point.count != 2 || !frame.contains(CGPoint(x: point[0], y: point[1])) {
                return false
            }
        }
        return true
    }

    static func rect(_ box: [Double]) -> CGRect {
        guard box.count == 4 else { return .zero }
        return CGRect(x: box[0], y: box[1], width: box[2], height: box[3])
    }

    /// The example as the pictures draw it.
    func showcase(imageURL: URL) -> StageShowcase {
        // Typed one by one: one long initializer of mapping closures can outrun the type checker.
        let shownRegions: [StageShowcase.Region] = regions.map { region in
            StageShowcase.Region(kind: region.kind, box: Self.rect(region.box))
        }
        var shownLines: [StageShowcase.Line] = []
        for line in lines {
            let baseline: [CGPoint] = line.baseline.map { point in CGPoint(x: point[0], y: point[1]) }
            shownLines.append(StageShowcase.Line(box: Self.rect(line.box), baseline: baseline, text: line.text))
        }
        let shownStatements: [StageShowcase.Statement] = statements.map { said in
            StageShowcase.Statement(subject: said.subject, object: said.object, label: said.label)
        }
        let shownExpansions: [StageShowcase.Expansion] = normalise.map { expansion in
            StageShowcase.Expansion(line: expansion.line, written: expansion.written, expanded: expansion.expanded)
        }
        let shownTable: [StageShowcase.Cell] = table.map { cell in
            StageShowcase.Cell(field: cell.field, value: cell.value, from: cell.from, box: cell.box.map(Self.rect))
        }
        let shownTranslation: (line: Int, text: String) = (translation.line, translation.text)
        let shownSearch: (query: String, matches: [StageShowcase.Mark]) = (search.query, search.matches)
        return StageShowcase(
            picture: .bundled(imageURL), size: CGSize(width: width, height: height),
            regions: shownRegions, lines: shownLines, names: names, dates: dates, statements: shownStatements,
            passage: passage.lines, expansions: shownExpansions, translation: shownTranslation, table: shownTable,
            search: shownSearch, credit: shortCredit, licenceURL: URL(string: licenceUrl),
            sourceURL: URL(string: source)
        )
    }
}

// MARK: - Which page a stage's picture plays on

/// Picks the page a stage's picture plays on (`source.onboard.stages.shows-what-it-does`): the person's own sample
/// page when the stage's try made something on it, else the example shipped with the app.
enum StageShowcaseSource {
    /// The sample page the try read, with its reading, names and statements; nil when the try made nothing to show.
    static func own(from result: SetupStageTryResult?) -> StageShowcase? {
        guard let result else { return nil }
        return own(pages: result.perPage ?? [], names: result.names ?? [])
    }

    /// A sample page from a try's pages and names (a try's, or one candidate's).
    static func own(pages: [SetupStageTryResult.Page], names found: [SetupStageTryResult.Name]) -> StageShowcase? {
        let read: SetupStageTryResult.Page? = pages.first { page in !(page.readings ?? []).isEmpty }
        guard let page = read ?? pages.first else { return nil }
        let reading: String = page.readings?.first?.text ?? ""
        let pieces: [Substring] = reading.split(separator: "\n", omittingEmptySubsequences: true)
        var lines: [StageShowcase.Line] = []
        for piece in pieces { lines.append(StageShowcase.Line(box: nil, baseline: nil, text: String(piece))) }
        var names: [StageShowcase.Mark] = []
        for name in found { names += marks(of: name.name, kind: name.type, in: lines) }
        var statements: [StageShowcase.Statement] = []
        for said in page.statements ?? [] { statements.append(StageShowcase.Statement(subject: nil, object: nil, label: said)) }
        return StageShowcase(
            picture: .sample(pageId: page.id), size: nil, regions: [], lines: lines, names: names, dates: [],
            statements: statements, passage: [], expansions: [], translation: nil, table: [], search: nil,
            credit: nil, licenceURL: nil, sourceURL: nil
        )
    }

    /// The page to play: the try's, else the example (nil only when the app's example is missing).
    static func showcase(for result: SetupStageTryResult?,
                         example: (example: StageShowcaseExample, imageURL: URL)? = StageShowcaseExample.bundled()) -> StageShowcase? {
        own(from: result) ?? example.map { $0.example.showcase(imageURL: $0.imageURL) }
    }

    /// Every place `word` occurs in the lines, as marks.
    static func marks(of word: String, kind: String?, in lines: [StageShowcase.Line]) -> [StageShowcase.Mark] {
        guard !word.isEmpty else { return [] }
        return lines.enumerated().flatMap { index, line -> [StageShowcase.Mark] in
            var found: [StageShowcase.Mark] = []
            var searchStart = line.text.startIndex
            while let range = line.text.range(of: word, range: searchStart..<line.text.endIndex) {
                let start = line.text.distance(from: line.text.startIndex, to: range.lowerBound)
                found.append(.init(line: index, start: start, end: start + word.count, kind: kind))
                searchStart = range.upperBound
            }
            return found
        }
    }
}
