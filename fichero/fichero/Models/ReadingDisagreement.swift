import Foundation
import Observation
import SwiftUI

/// Where a page's readers disagree (#5665, `source.disagree.route`): the engine's
/// `GET /api/documents/{page_id}/disagreement`, word by word. Agreement, never accuracy: the share of readers that
/// gave each word of the line's medoid reading, after every reading was brought to one convention (`normalisedAs`).
/// The app works nothing out but the order it walks the words in and the tint it draws.
struct ReadingDisagreement: Decodable, Equatable {
    struct Reader: Decodable, Equatable {
        let id: String
        let label: String
    }

    struct Variant: Decodable, Equatable {
        let text: String
        let readers: [String]
    }

    struct Word: Decodable, Equatable {
        let text: String
        let charStart: Int
        let charEnd: Int
        /// `[x, y, width, height]` in the page image's pixels, when the reading places the word.
        let bbox: [Double]?
        /// The share of readers that gave exactly this word, 0–1.
        let agreement: Double
        let variants: [Variant]
    }

    struct Line: Decodable, Equatable {
        let segmentId: String
        let referenceReader: String?
        let text: String?
        let agreement: Double
        let words: [Word]
    }

    /// One word's place on the page: its line, then its place in the line.
    struct WordRef: Hashable, Comparable {
        let line: Int
        let word: Int

        static func < (lhs: WordRef, rhs: WordRef) -> Bool {
            (lhs.line, lhs.word) < (rhs.line, rhs.word)
        }
    }

    /// One row of a word's popover: a variant, who gave it, and how many of how many.
    struct VariantRow: Equatable {
        let text: String
        let readers: String
        let count: String
    }

    let pageId: String?
    let readers: [Reader]
    let pageAgreement: Double?
    let normalisedAs: String?
    let lines: [Line]

    /// The engine's snake_case, read as the app's names.
    static func decode(_ data: Data) throws -> ReadingDisagreement {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ReadingDisagreement.self, from: data)
    }

    /// Two readings or more: there is something to compare (`source.disagree.fewer-than-two`).
    var isComparable: Bool { readers.count >= 2 }

    /// Every word, in reading order: line by line, word by word.
    var wordRefs: [WordRef] {
        lines.indices.flatMap { line in lines[line].words.indices.map { WordRef(line: line, word: $0) } }
    }

    func word(_ ref: WordRef) -> Word? {
        guard lines.indices.contains(ref.line), lines[ref.line].words.indices.contains(ref.word) else { return nil }
        return lines[ref.line].words[ref.word]
    }

    /// A word below unanimous is doubtful (`source.disagree.next-doubtful`).
    static func isDoubtful(_ word: Word) -> Bool { word.agreement < 1 - 1e-9 }

    /// The doubtful words, in reading order.
    var doubtfulRefs: [WordRef] { wordRefs.filter { word($0).map(Self.isDoubtful) ?? false } }

    /// The next doubtful word after `ref` (the first with none), wrapping at the page's end; nil with none.
    func doubtful(after ref: WordRef?) -> WordRef? {
        let doubtful = doubtfulRefs
        guard let ref else { return doubtful.first }
        return doubtful.first { $0 > ref } ?? doubtful.first
    }

    /// The doubtful word before `ref` (the last with none), wrapping at the page's start; nil with none.
    func doubtful(before ref: WordRef?) -> WordRef? {
        let doubtful = doubtfulRefs
        guard let ref else { return doubtful.last }
        return doubtful.last { $0 < ref } ?? doubtful.last
    }

    /// A word's popover rows (`source.disagree.popover`): each variant, most readers first (the engine's order
    /// kept among equals), the readers by label, and how many of how many; a reader that gave nothing reads as
    /// "(nothing)".
    func variantRows(for word: Word) -> [VariantRow] {
        let labels = Dictionary(readers.map { ($0.id, $0.label) }, uniquingKeysWith: { first, _ in first })
        let ordered = word.variants.enumerated().sorted { lhs, rhs in
            lhs.element.readers.count != rhs.element.readers.count
                ? lhs.element.readers.count > rhs.element.readers.count : lhs.offset < rhs.offset
        }
        return ordered.map { _, variant in
            VariantRow(text: variant.text.isEmpty ? "(nothing)" : variant.text,
                       readers: variant.readers.map { labels[$0] ?? $0 }.joined(separator: ", "),
                       count: "\(variant.readers.count) of \(readers.count)")
        }
    }

    /// An agreement figure in words: "82% agreement".
    static func percent(_ agreement: Double) -> String {
        agreement.formatted(.percent.precision(.fractionLength(0))) + " agreement"
    }
}

/// How a word is tinted by its agreement (`source.disagree.lens`): plain when unanimous, yellow from 0.6 up to 1,
/// red below 0.6.
enum DisagreementTint: Equatable {
    case unanimous, some, most

    /// Below this, most readers did not give the word: red.
    static let redBelow = 0.6

    static func of(_ agreement: Double) -> DisagreementTint {
        if agreement >= 1 - 1e-9 { return .unanimous }
        return agreement >= redBelow ? .some : .most
    }

    var color: Color {
        switch self {
        case .unanimous: .clear
        case .some: .yellow.opacity(0.35)
        case .most: .red.opacity(0.35)
        }
    }
}

/// What the engine could not give, in words.
enum ReadingDisagreementUnavailable: LocalizedError, Equatable {
    /// The engine has no disagreement route yet (#5665's engine half).
    case notYetBuilt

    var errorDescription: String? { "Fichero cannot compare this page's readers yet." }
}

/// A project's pages' disagreement, read once per page and kept, with the word selected on each
/// (`source.disagree.*`). One per project (`LibraryReference.disagreementStore`).
@MainActor
@Observable
final class ReadingDisagreementStore {
    enum State: Equatable {
        case loading
        case loaded(ReadingDisagreement)
        case unavailable(String)
    }

    /// Reads one page's disagreement. Until the engine's route exists, `notYetBuilt`.
    typealias Source = @MainActor (String) async throws -> ReadingDisagreement

    /// The source before the engine has the route: it says so.
    static let notYetBuilt: Source = { _ in throw ReadingDisagreementUnavailable.notYetBuilt }

    private(set) var pages: [String: State] = [:]
    /// The word selected on each page, by page id.
    var selected: [String: ReadingDisagreement.WordRef] = [:]
    private let source: Source

    init(source: @escaping Source = ReadingDisagreementStore.notYetBuilt) {
        self.source = source
    }

    func disagreement(of pageId: String) -> ReadingDisagreement? {
        if case .loaded(let disagreement) = pages[pageId] { return disagreement }
        return nil
    }

    func load(pageId: String) async {
        if pages[pageId] == nil { pages[pageId] = .loading }
        do {
            let found = try await source(pageId)
            if pages[pageId] != .loaded(found) { pages[pageId] = .loaded(found) }
        } catch {
            if error.isCancellationError { return }
            pages[pageId] = .unavailable(error.localizedDescription)
        }
    }

    /// Move the selection to the next doubtful word; false with none.
    @discardableResult
    func selectNextDoubtful(on pageId: String) -> Bool {
        guard let next = disagreement(of: pageId)?.doubtful(after: selected[pageId]) else { return false }
        selected[pageId] = next
        return true
    }

    /// Move the selection to the previous doubtful word; false with none.
    @discardableResult
    func selectPreviousDoubtful(on pageId: String) -> Bool {
        guard let previous = disagreement(of: pageId)?.doubtful(before: selected[pageId]) else { return false }
        selected[pageId] = previous
        return true
    }
}
