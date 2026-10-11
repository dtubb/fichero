import SwiftUI

/// Where a page's pixels land in a stage's picture: the page fitted into the space, and the scale from its pixels
/// to points. Pure, so the stage views and the tests share it.
struct ShowcaseGeometry: Equatable {
    /// The page's rectangle in the view.
    let drawn: CGRect
    /// Points per pixel.
    let scale: CGFloat

    /// `imageSize` fitted into `space`, centred.
    init(imageSize: CGSize, in space: CGSize) {
        let width = max(imageSize.width, 1), height = max(imageSize.height, 1)
        let scale = min(space.width / width, space.height / height)
        let size = CGSize(width: width * scale, height: height * scale)
        drawn = CGRect(x: (space.width - size.width) / 2, y: (space.height - size.height) / 2,
                       width: size.width, height: size.height)
        self.scale = scale
    }

    func rect(_ pixels: CGRect) -> CGRect {
        CGRect(x: drawn.minX + pixels.minX * scale, y: drawn.minY + pixels.minY * scale,
               width: pixels.width * scale, height: pixels.height * scale)
    }

    func point(_ pixels: CGPoint) -> CGPoint {
        CGPoint(x: drawn.minX + pixels.x * scale, y: drawn.minY + pixels.y * scale)
    }
}

/// The page every stage's picture draws over (`source.onboard.stages.shows-what-it-does`): the example's picture from
/// the app bundle, or the person's own sample page from the project's storage, fitted into the space; the stage's
/// marks go on top, placed through the geometry. A page known only by its text (a sample page whose reading has no
/// boxes) shows its picture and nothing is drawn on it.
struct StagePageLayer<Overlay: View>: View {
    let showcase: StageShowcase
    @ViewBuilder var overlay: (ShowcaseGeometry) -> Overlay

    /// A page's proportions when its size is not known (a sample page): a portrait leaf.
    static var portrait: CGSize { CGSize(width: 3, height: 4) }

    var body: some View {
        GeometryReader { proxy in
            let geometry = ShowcaseGeometry(imageSize: showcase.size ?? Self.portrait, in: proxy.size)
            ZStack(alignment: .topLeading) {
                picture
                    .frame(width: geometry.drawn.width, height: geometry.drawn.height)
                    .clipShape(RoundedRectangle(cornerRadius: 3))
                    .shadow(color: .black.opacity(0.15), radius: 2, y: 1)
                    .position(x: geometry.drawn.midX, y: geometry.drawn.midY)
                overlay(geometry)
            }
        }
    }

    @ViewBuilder
    private var picture: some View {
        switch showcase.picture {
        case .bundled(let url):
            if let image = ShowcasePictures.image(at: url) {
                Image(platformImage: image).resizable().aspectRatio(contentMode: .fit)
            } else {
                Rectangle().fill(.quaternary)
            }
        case .sample(let pageId):
            LibraryImageView(documentId: pageId, imageType: .display)
                .aspectRatio(contentMode: .fit)
        }
    }
}

/// The example's picture, read from the bundle once.
@MainActor
enum ShowcasePictures {
    private static var cache: [URL: PlatformImage] = [:]

    static func image(at url: URL) -> PlatformImage? {
        if let cached = cache[url] { return cached }
        guard let image = PlatformImage(contentsOfFile: url.path) else { return nil }
        cache[url] = image
        return image
    }
}

extension View {
    /// A light sweeping down the page, `progress` 0 at the top to 1 at the foot (the one Metal shader,
    /// `ScanSweep.metal`, used by Prepare Images and Read).
    func scanSweep(progress: Double, height: CGFloat, band: CGFloat = 26, lift: Double = 0.28) -> some View {
        colorEffect(ShaderLibrary.scanSweep(.float(Float(progress) * Float(height)), .float(Float(band)),
                                            .float(Float(lift))))
    }
}

/// The example's credit under it (CC BY-SA asks for it where the person sees the page): "Example: BNE · DILE,
/// CC BY-SA 4.0", linked to the licence. Nothing on the person's own page.
struct ShowcaseCredit: View {
    let showcase: StageShowcase

    var body: some View {
        if let credit = showcase.credit {
            if let url = showcase.licenceURL {
                Link(credit, destination: url).font(.caption2).foregroundStyle(.secondary)
            } else {
                Text(credit).font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}

#Preview("The example page, its lines outlined") {
    if let example = StageShowcaseExample.bundled() {
        let showcase = example.example.showcase(imageURL: example.imageURL)
        VStack {
            StagePageLayer(showcase: showcase) { geometry in
                ForEach(showcase.lines.indices, id: \.self) { index in
                    if let box = showcase.lines[index].box {
                        let rect = geometry.rect(box)
                        Rectangle().stroke(.blue.opacity(0.6))
                            .frame(width: rect.width, height: rect.height)
                            .position(x: rect.midX, y: rect.midY)
                    }
                }
            }
            .frame(width: 360, height: 220)
            ShowcaseCredit(showcase: showcase)
        }
        .padding()
    }
}
