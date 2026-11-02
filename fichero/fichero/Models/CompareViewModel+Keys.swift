import FicheroAPIClient
import Foundation

/// The compare view's keys, pager and spoken labels (`wide.compare.keyboard-and-voiceover`, `wide.compare.compact-layout`, #5900). Pure: the
/// key map is a table, the layout a rule per platform, the labels functions of the engine's answer.
extension CompareViewModel {
    enum Key: Equatable {
        case left, right, up, down, `return`, escape
        case digit(Int)
    }

    enum Command: Equatable {
        case previousCandidate, nextCandidate, previousLine, nextLine, nextDifferingLine
        case showCandidate(Int)  // 1-based; 0 shows all
        case useThis, close
    }

    /// ←/→ the candidate (or the wipe handle), ↑/↓ the line, ⌥↓ the next differing line, 1–3 one candidate or all (0), Return Use This, Esc close.
    static func command(for key: Key, option: Bool) -> Command? {
        switch key {
        case .left: return .previousCandidate
        case .right: return .nextCandidate
        case .up: return .previousLine
        case .down: return option ? .nextDifferingLine : .nextLine
        case .digit(let number): return (0...3).contains(number) ? .showCandidate(number) : nil
        case .return: return .useThis
        case .escape: return .close
        }
    }

    /// What a command asks of the view once the model has moved.
    enum Outcome: Equatable {
        case moved, useThis(readerId: String, line: Int), close, nothing
    }

    /// Wipe's handle moves a twentieth a key press.
    static let handleStep = 0.05

    mutating func apply(_ command: Command) -> Outcome {
        switch command {
        case .previousCandidate, .nextCandidate:
            let step = command == .nextCandidate ? 1 : -1
            if mode == .wipe {
                moveHandle(to: handle + Double(step) * Self.handleStep)
                return .moved
            }
            guard readers.count > 1 else { return .nothing }
            candidate = min(readers.count - 1, max(0, (candidate ?? (step > 0 ? -1 : readers.count)) + step))
            return .moved
        case .previousLine, .nextLine:
            return focus(at: (rowIndex ?? (command == .nextLine ? -1 : rows.count)) + (command == .nextLine ? 1 : -1))
        case .nextDifferingLine:
            let list = rows
            let from = (rowIndex ?? -1) + 1
            guard let next = list.indices.dropFirst(from).first(where: { list[$0].differs }) else { return .nothing }
            return focus(at: next)
        case .showCandidate(let number):
            candidate = number == 0 || number > readers.count ? nil : number - 1
            return .moved
        case .useThis:
            guard let line = focusedLine, let row = rows.first(where: { $0.id == line }), row.canPick,
                  let reader = visibleReaders.first(where: { reader in
                      guard let index = readers.firstIndex(where: { $0.id == reader.id }) else { return false }
                      return row.texts[index] != nil && reader.id != row.countingReaderId
                  }) else { return .nothing }
            return .useThis(readerId: reader.id, line: line)
        case .close:
            return .close
        }
    }

    private var rowIndex: Int? { focusedLine.flatMap { line in rows.firstIndex { $0.id == line } } }

    private mutating func focus(at index: Int) -> Outcome {
        let list = rows
        guard list.indices.contains(index) else { return .nothing }
        focusedLine = list[index].id
        return .moved
    }

    // MARK: Compact layout

    /// iPad and iPhone show the columns as a horizontal pager of candidates with the line list under; the Mac shows them all.
    static func usesPager(_ platform: Platform) -> Bool { platform != .mac }

    /// The readers the columns show: all, or the one candidate.
    var visibleReaders: [Components.Schemas.CompareReader] {
        guard let candidate, readers.indices.contains(candidate) else { return readers }
        return [readers[candidate]]
    }

    /// The sample strip's dots, one per candidate, the current one marked.
    var pagerDots: [Bool] { readers.indices.map { $0 == candidate } }

    // MARK: Spoken labels

    /// A column is one element: its name and its figures.
    func columnLabel(_ reader: Components.Schemas.CompareReader) -> String {
        if let why = notReadBecause(reader: reader.id) { return "\(reader.label). \(why)" }
        return reader.label
    }

    /// A cell reads "<reader>: <text>".
    func cellLabel(reader: Components.Schemas.CompareReader, text: String?) -> String {
        "\(reader.label): \(text ?? "no reading")"
    }

    /// A row announces agree or differ.
    func rowAnnouncement(_ row: Row) -> String {
        row.differs ? "Line \(row.id + 1): the readers differ" : "Line \(row.id + 1): the readers agree"
    }
}
