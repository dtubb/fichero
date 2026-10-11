import SwiftUI

// The pictures of the stages that work on the page itself (#5668, `source.onboard.stages.shows-what-it-does`):
// Prepare Images, Find Regions, Find Lines, Read, Normalise, Translate, Organise. Each draws one frame from
// `progress`, 0 to 1; `StageShowcaseView` plays them.

/// Prepare Images: a tilted, dim scan straightens, crops and brightens, a light sweeping down it.
struct PrepareImagesPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let settle = StageShowcasePlayback.phase(progress, from: 0, to: 0.6)
        let sweep = StageShowcasePlayback.phase(progress, from: 0.35, to: 1)
        GeometryReader { proxy in
            StagePageLayer(showcase: showcase) { _ in EmptyView() }
                .rotationEffect(.degrees(-7 * (1 - settle)))
                .scaleEffect(1.12 - 0.12 * settle)
                .brightness(-0.22 * (1 - settle))
                .contrast(0.75 + 0.25 * settle)
                .scanSweep(progress: sweep, height: proxy.size.height)
                .padding(8 * settle)
        }
    }
}

/// Find Regions: the page's blocks outlined one after another.
struct FindRegionsPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        StagePageLayer(showcase: showcase) { geometry in
            ForEach(Array(showcase.regions.enumerated()), id: \.offset) { index, region in
                let share = 1 / Double(max(1, showcase.regions.count))
                let drawn = StageShowcasePlayback.phase(progress, from: Double(index) * share * 0.8,
                                                        to: Double(index) * share * 0.8 + share)
                let rect = geometry.rect(region.box)
                Rectangle()
                    .trim(from: 0, to: drawn)
                    .stroke(ShowcaseStyle.colour(forRegion: region.kind), lineWidth: 2)
                    .background(ShowcaseStyle.colour(forRegion: region.kind).opacity(0.12 * drawn))
                    .frame(width: rect.width, height: rect.height)
                    .position(x: rect.midX, y: rect.midY)
            }
        }
    }
}

/// Find Lines: each baseline drawn from left to right, line after line.
struct FindLinesPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        StagePageLayer(showcase: showcase) { geometry in
            let lines = showcase.lines.compactMap(\.baseline)
            ForEach(Array(lines.enumerated()), id: \.offset) { index, baseline in
                let start = 0.85 * Double(index) / Double(max(1, lines.count))
                let drawn = StageShowcasePlayback.phase(progress, from: start, to: start + 0.25)
                Path { path in
                    guard let first = baseline.first else { return }
                    path.move(to: geometry.point(first))
                    for point in baseline.dropFirst() { path.addLine(to: geometry.point(point)) }
                }
                .trim(from: 0, to: drawn)
                .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
            }
        }
    }
}

/// Read: the reading types in line by line beside the page, a light sweeping the line being read.
struct ReadPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let texts = showcase.lines.map(\.text)
        let total = texts.reduce(0) { $0 + $1.count }
        let revealed = Int(Double(total) * StageShowcasePlayback.phase(progress, from: 0.05, to: 0.95))
        HStack(spacing: 8) {
            GeometryReader { proxy in
                StagePageLayer(showcase: showcase) { _ in EmptyView() }
                    .scanSweep(progress: Double(revealed) / Double(max(1, total)), height: proxy.size.height, band: 14)
            }
            ShowcaseTextColumn(lines: texts, revealed: revealed)
        }
        .padding(8)
    }
}

/// Normalise: the abbreviated words of a line become their expanded forms ("q́" into "que").
struct NormalisePicture: View {
    let showcase: StageShowcase
    let progress: Double

    /// The line with every expansion made.
    static func expanded(_ text: String, _ expansions: [StageShowcase.Expansion]) -> String {
        expansions.reduce(text) { line, expansion in
            line.replacingOccurrences(of: expansion.written, with: expansion.expanded)
        }
    }

    var body: some View {
        let line = showcase.expansions.first?.line ?? 0
        let text = showcase.lines.indices.contains(line) ? showcase.lines[line].text : ""
        let change = StageShowcasePlayback.phase(progress, from: 0.3, to: 0.8)
        ShowcaseBeforeAfter(before: text, after: Self.expanded(text, showcase.expansions), change: change,
                            caption: "As written  →  Abbreviations expanded")
    }
}

/// Translate: a line crossfades into its translation.
struct TranslatePicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let line = showcase.translation?.line ?? 0
        let text = showcase.lines.indices.contains(line) ? showcase.lines[line].text : ""
        let change = StageShowcasePlayback.phase(progress, from: 0.3, to: 0.8)
        ShowcaseBeforeAfter(before: text, after: showcase.translation?.text ?? text, change: change,
                            caption: "Spanish  →  English")
    }
}

/// A line before and after, the one crossfading into the other.
struct ShowcaseBeforeAfter: View {
    let before: String
    let after: String
    let change: Double
    let caption: String

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                Text(before).opacity(1 - change).blur(radius: 3 * change)
                Text(after).opacity(change).blur(radius: 3 * (1 - change))
            }
            .font(.title3)
            .multilineTextAlignment(.center)
            Text(caption).font(.caption).foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Organise: page thumbnails slide together into dashed document groups.
struct OrganisePicture: View {
    let showcase: StageShowcase
    let progress: Double

    /// One thumbnail: where it starts and ends, as shares of the space, and which document it joins.
    struct Thumbnail {
        let start: CGPoint
        let end: CGPoint
        let group: Int
    }

    static let thumbnails: [Thumbnail] = [
        Thumbnail(start: CGPoint(x: 0.12, y: 0.3), end: CGPoint(x: 0.2, y: 0.5), group: 0),
        Thumbnail(start: CGPoint(x: 0.4, y: 0.75), end: CGPoint(x: 0.32, y: 0.5), group: 0),
        Thumbnail(start: CGPoint(x: 0.6, y: 0.25), end: CGPoint(x: 0.44, y: 0.5), group: 0),
        Thumbnail(start: CGPoint(x: 0.85, y: 0.7), end: CGPoint(x: 0.66, y: 0.5), group: 1),
        Thumbnail(start: CGPoint(x: 0.3, y: 0.15), end: CGPoint(x: 0.78, y: 0.5), group: 1)
    ]

    var body: some View {
        let move = StageShowcasePlayback.phase(progress, from: 0, to: 0.65)
        let group = StageShowcasePlayback.phase(progress, from: 0.6, to: 1)
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                ForEach([0, 1], id: \.self) { index in
                    let members = Self.thumbnails.filter { $0.group == index }.map(\.end.x)
                    let left = (members.min() ?? 0) * size.width - 32, right = (members.max() ?? 0) * size.width + 32
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(.secondary, style: StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
                        .frame(width: right - left, height: size.height * 0.5)
                        .position(x: (left + right) / 2, y: size.height * 0.5)
                        .opacity(group)
                }
                ForEach(Array(Self.thumbnails.enumerated()), id: \.offset) { _, thumbnail in
                    let across = thumbnail.start.x + (thumbnail.end.x - thumbnail.start.x) * move
                    let down = thumbnail.start.y + (thumbnail.end.y - thumbnail.start.y) * move
                    StagePageLayer(showcase: showcase) { _ in EmptyView() }
                        .frame(width: 44, height: 62)
                        .position(x: across * size.width, y: down * size.height)
                }
            }
        }
    }
}

/// Colours the pictures share.
enum ShowcaseStyle {
    static func colour(forKind kind: String?) -> Color {
        switch kind {
        case "person": .blue
        case "place": .green
        case "organisation", "organization": .purple
        case "date": .orange
        default: .teal
        }
    }

    static func colour(forRegion kind: String) -> Color {
        switch kind {
        case "text": .accentColor
        case "margin": .orange
        case "folio": .purple
        default: .teal
        }
    }
}

#Preview("Prepare Images · Find Regions · Find Lines") {
    if let example = StageShowcaseExample.bundled() {
        let showcase = example.example.showcase(imageURL: example.imageURL)
        HStack {
            PrepareImagesPicture(showcase: showcase, progress: 0.4).frame(width: 220, height: 220)
            FindRegionsPicture(showcase: showcase, progress: 0.7).frame(width: 220, height: 220)
            FindLinesPicture(showcase: showcase, progress: 0.6).frame(width: 220, height: 220)
        }
        .padding()
    }
}

#Preview("Read · Normalise · Translate · Organise") {
    if let example = StageShowcaseExample.bundled() {
        let showcase = example.example.showcase(imageURL: example.imageURL)
        VStack {
            ReadPicture(showcase: showcase, progress: 0.5).frame(width: 360, height: 220)
            NormalisePicture(showcase: showcase, progress: 1).frame(width: 360, height: 120)
            TranslatePicture(showcase: showcase, progress: 0.5).frame(width: 360, height: 120)
            OrganisePicture(showcase: showcase, progress: 1).frame(width: 360, height: 220)
        }
        .padding()
    }
}
