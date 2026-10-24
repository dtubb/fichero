import SwiftUI

// The pictures of the stages that work on what the page says (#5668, `source.onboard.stages.shows-what-it-does`):
// Names, Statements, Dates & Times, Passages, Structured Data, Search. On the example page they draw on the page; on a
// sample page whose reading has no boxes they draw on its text beside the picture.

/// A mark lit in a colour.
struct ShowcaseLit {
    let mark: StageShowcase.Mark
    let colour: Color
}

/// Lights `marks` on the page (or on the text beside it), each in its colour, appearing one after another.
struct ShowcaseMarksPicture: View {
    let showcase: StageShowcase
    let marks: [ShowcaseLit]
    let progress: Double

    /// The marks as the text column lights them, at this frame.
    private var textHighlights: [ShowcaseLit] {
        var lit: [ShowcaseLit] = []
        for (index, item) in marks.enumerated() {
            lit.append(ShowcaseLit(mark: item.mark, colour: item.colour.opacity(0.35 * self.lit(index))))
        }
        return lit
    }

    func lit(_ index: Int) -> Double {
        let start = 0.7 * Double(index) / Double(max(1, marks.count))
        return StageShowcasePlayback.phase(progress, from: start, to: start + 0.3)
    }

    var body: some View {
        if showcase.lines.contains(where: { $0.box != nil }) {
            StagePageLayer(showcase: showcase) { geometry in
                ForEach(Array(marks.enumerated()), id: \.offset) { index, item in
                    if let box = showcase.box(of: item.mark) {
                        let rect = geometry.rect(box)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(item.colour.opacity(0.35 * lit(index)))
                            .overlay(RoundedRectangle(cornerRadius: 3).stroke(item.colour.opacity(lit(index))))
                            .frame(width: rect.width, height: rect.height)
                            .position(x: rect.midX, y: rect.midY)
                    }
                }
            }
        } else {
            HStack(spacing: 8) {
                StagePageLayer(showcase: showcase) { _ in EmptyView() }
                ShowcaseTextColumn(lines: showcase.lines.map(\.text), highlights: textHighlights)
            }
            .padding(8)
        }
    }
}

/// Names: the names light up, coloured by kind.
struct NamesPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        ShowcaseMarksPicture(showcase: showcase,
                             marks: showcase.names.map { ShowcaseLit(mark: $0, colour: ShowcaseStyle.colour(forKind: $0.kind)) },
                             progress: progress)
    }
}

/// Statements: the names light, then an arrow joins the two a statement links, with what it says.
struct StatementsPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let ends = showcase.statements.flatMap { [$0.subject, $0.object].compactMap { $0 } }
        let arrow = StageShowcasePlayback.phase(progress, from: 0.35, to: 0.85)
        ZStack {
            ShowcaseMarksPicture(showcase: showcase, marks: ends.map { ShowcaseLit(mark: $0, colour: .blue) },
                                 progress: min(1, progress * 2))
            StagePageLayer(showcase: showcase, drawsPicture: false) { geometry in
                ForEach(Array(showcase.statements.enumerated()), id: \.offset) { _, said in
                    if let subjectBox = said.subject.flatMap(showcase.box(of:)),
                       let objectBox = said.object.flatMap(showcase.box(of:)) {
                        let start = geometry.point(CGPoint(x: subjectBox.midX, y: subjectBox.maxY))
                        let end = geometry.point(CGPoint(x: objectBox.midX, y: objectBox.minY))
                        ShowcaseArrow(start: start, end: end, drawn: arrow)
                        Text(said.label)
                            .font(.caption2)
                            .padding(.horizontal, 4)
                            .background(.thinMaterial, in: Capsule())
                            .position(x: (start.x + end.x) / 2 + 40, y: (start.y + end.y) / 2)
                            .opacity(arrow)
                    }
                }
            }
            if !showcase.lines.contains(where: { $0.box != nil }), let said = showcase.statements.first {
                Text(said.label).font(.callout).padding(6).background(.thinMaterial, in: Capsule()).opacity(arrow)
            }
        }
    }
}

/// An arrow from `start` to `end`, drawn as far as `drawn`.
struct ShowcaseArrow: View {
    let start: CGPoint
    let end: CGPoint
    let drawn: Double

    var body: some View {
        let control = CGPoint(x: max(start.x, end.x) + 40, y: (start.y + end.y) / 2)
        Path { path in
            path.move(to: start)
            path.addQuadCurve(to: end, control: control)
        }
        .trim(from: 0, to: drawn)
        .stroke(Color.blue, style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
    }
}

/// Dates & Times: the date words become date chips.
struct DatesPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let chip = StageShowcasePlayback.phase(progress, from: 0.3, to: 0.8)
        ZStack {
            ShowcaseMarksPicture(showcase: showcase, marks: showcase.dates.map { ShowcaseLit(mark: $0, colour: .orange) },
                                 progress: min(1, progress * 2.5))
            StagePageLayer(showcase: showcase, drawsPicture: false) { geometry in
                ForEach(Array(showcase.dates.enumerated()), id: \.offset) { _, date in
                    if let box = showcase.box(of: date) {
                        let rect = geometry.rect(box)
                        Label(date.value ?? showcase.text(of: date) ?? "", systemImage: "calendar")
                            .font(.caption)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.orange.opacity(0.9), in: Capsule())
                            .foregroundStyle(.white)
                            .scaleEffect(0.6 + 0.4 * chip)
                            .position(x: rect.midX, y: rect.minY - 12 * chip)
                            .opacity(chip)
                    }
                }
            }
        }
    }
}

/// Passages: a passage lifts out of the page.
struct PassagesPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let lift = StageShowcasePlayback.phase(progress, from: 0.2, to: 0.8)
        let boxes = showcase.passage.compactMap { showcase.lines.indices.contains($0) ? showcase.lines[$0].box : nil }
        let text = showcase.passage.compactMap { showcase.lines.indices.contains($0) ? showcase.lines[$0].text : nil }
        HStack(spacing: 8) {
            StagePageLayer(showcase: showcase) { geometry in
                if let first = boxes.first {
                    let union = boxes.dropFirst().reduce(first) { $0.union($1) }
                    let rect = geometry.rect(union)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.accentColor.opacity(0.18))
                        .overlay(RoundedRectangle(cornerRadius: 3).stroke(Color.accentColor))
                        .frame(width: rect.width, height: rect.height)
                        .shadow(color: .black.opacity(0.25 * lift), radius: 6 * lift, y: 4 * lift)
                        .position(x: rect.midX, y: rect.midY - 10 * lift)
                        .opacity(lift)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Passage").font(.caption.weight(.semibold))
                ForEach(text, id: \.self) { Text($0).font(.caption) }
            }
            .padding(8)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 6))
            .opacity(lift)
            .offset(x: 20 * (1 - lift))
        }
        .padding(8)
    }
}

/// Structured Data: values from the page fill a table's cells.
struct StructuredDataPicture: View {
    let showcase: StageShowcase
    let progress: Double

    func filled(_ index: Int) -> Double {
        let start = 0.15 + 0.6 * Double(index) / Double(max(1, showcase.table.count))
        return StageShowcasePlayback.phase(progress, from: start, to: start + 0.25)
    }

    var body: some View {
        HStack(spacing: 10) {
            ShowcaseMarksPicture(showcase: showcase,
                                 marks: showcase.table.compactMap(\.from).map { ShowcaseLit(mark: $0, colour: .teal) },
                                 progress: min(1, progress * 2))
            Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 6) {
                ForEach(Array(showcase.table.enumerated()), id: \.offset) { index, cell in
                    GridRow {
                        Text(cell.field).font(.caption.weight(.medium))
                        Text(cell.value)
                            .font(.caption)
                            .padding(.horizontal, 4)
                            .frame(minWidth: 70, alignment: .leading)
                            .background(Color.teal.opacity(0.15 * filled(index)), in: RoundedRectangle(cornerRadius: 3))
                            .opacity(filled(index))
                            .offset(x: -30 * (1 - filled(index)))
                    }
                }
            }
            .padding(8)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 6))
        }
        .padding(8)
    }
}

/// Search: a query typed, then its matches lit on the page.
struct SearchPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let query = showcase.search?.query ?? ""
        let typed = Int(Double(query.count) * StageShowcasePlayback.phase(progress, from: 0, to: 0.35))
        VStack(spacing: 6) {
            Label(String(query.prefix(typed)), systemImage: "magnifyingglass")
                .font(.callout)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(.thinMaterial, in: Capsule())
            ShowcaseMarksPicture(showcase: showcase,
                                 marks: (showcase.search?.matches ?? []).map { ShowcaseLit(mark: $0, colour: .yellow) },
                                 progress: StageShowcasePlayback.phase(progress, from: 0.4, to: 1))
        }
        .padding(8)
    }
}

/// The page's text beside it: revealed up to `revealed` characters, with marks lit.
struct ShowcaseTextColumn: View {
    let lines: [String]
    var revealed = Int.max
    var highlights: [ShowcaseLit] = []

    /// One line as shown: cut at the characters revealed so far, its marks lit.
    static func line(_ text: String, index: Int, revealedBefore: Int, revealed: Int,
                     highlights: [ShowcaseLit]) -> AttributedString {
        let shown = String(text.prefix(max(0, revealed - revealedBefore)))
        var attributed = AttributedString(shown)
        for lit in highlights where lit.mark.line == index && lit.mark.end <= shown.count {
            let start = attributed.index(attributed.startIndex, offsetByCharacters: lit.mark.start)
            let end = attributed.index(attributed.startIndex, offsetByCharacters: lit.mark.end)
            attributed[start..<end].backgroundColor = lit.colour
        }
        return attributed
    }

    var body: some View {
        let before = lines.indices.map { index in lines[..<index].reduce(0) { $0 + $1.count } }
        VStack(alignment: .leading, spacing: 2) {
            ForEach(lines.indices, id: \.self) { index in
                Text(Self.line(lines[index], index: index, revealedBefore: before[index], revealed: revealed,
                               highlights: highlights))
                    .font(.caption2)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

#Preview("Names · Statements · Dates") {
    if let example = StageShowcaseExample.bundled() {
        let showcase = example.example.showcase(imageURL: example.imageURL)
        HStack {
            NamesPicture(showcase: showcase, progress: 1).frame(width: 220, height: 220)
            StatementsPicture(showcase: showcase, progress: 1).frame(width: 220, height: 220)
            DatesPicture(showcase: showcase, progress: 1).frame(width: 220, height: 220)
        }
        .padding()
    }
}

#Preview("Passages · Structured Data · Search") {
    if let example = StageShowcaseExample.bundled() {
        let showcase = example.example.showcase(imageURL: example.imageURL)
        VStack {
            PassagesPicture(showcase: showcase, progress: 1).frame(width: 360, height: 220)
            StructuredDataPicture(showcase: showcase, progress: 1).frame(width: 360, height: 220)
            SearchPicture(showcase: showcase, progress: 1).frame(width: 360, height: 220)
        }
        .padding()
    }
}

/// Catalogue: a folder's archival record fills in field by field (`catalogue.folder-description-fields`, #6087). The
/// fields are the engine's own, fixed; nothing here reads a page, so one picture serves every project.
struct CataloguePicture: View {
    let progress: Double

    static let fields: [(name: String, value: String)] = [
        ("Title", "Letters, 1782–1790"), ("Dates", "1782 to 1790"), ("Extent", "214 pages"),
        ("Scope and content", "Letters between the named parties, in Spanish."), ("Language and script", "Spanish, Latin")
    ]

    func filled(_ index: Int) -> Double {
        let start = 0.1 + 0.7 * Double(index) / Double(Self.fields.count)
        return StageShowcasePlayback.phase(progress, from: start, to: start + 0.2)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Folder", systemImage: "folder").font(.callout.weight(.medium))
            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
                ForEach(Array(Self.fields.enumerated()), id: \.offset) { index, field in
                    GridRow(alignment: .firstTextBaseline) {
                        Text(field.name).font(.caption.weight(.medium)).foregroundStyle(.secondary)
                        Text(field.value)
                            .font(.caption)
                            .opacity(filled(index))
                            .offset(x: -20 * (1 - filled(index)))
                    }
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 6))
        .padding(8)
    }
}
