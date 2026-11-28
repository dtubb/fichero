import SwiftUI

extension ContentView {
    /// The iPhone's item view: Source, Reader, Segments and Info as pages of one horizontal pager, with a segmented
    /// header in the bar's centre (`ios.item.pages`, `ios.item.header-says-where`, #6947). The pages are the panes
    /// the Mac already has. They mount when first scrolled near, not all four on push.
    @ViewBuilder
    var compactItemPages: some View {
        let page = compactItemPageBinding
        ScrollView(.horizontal) {
            LazyHStack(spacing: 0) {
                ForEach(ItemPage.allCases) { itemPage in
                    compactItemPageContent(itemPage)
                        .containerRelativeFrame(.horizontal)
                        .id(itemPage)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: Binding<ItemPage?>(
            get: { page.wrappedValue },
            set: { if let new = $0 { page.wrappedValue = new } }
        ))
        .scrollIndicators(.hidden)
        // A zoomed picture and the Segments page keep their drags (`ItemPage.swipePages`).
        .scrollDisabled(!page.wrappedValue.swipePages(imageZoomed: windowState.compactImageZoomed))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // The name stays as the title Back reads, but the bar draws the header instead (`ios.titles.once-at-most`).
        .navigationTitle(pushedReaderDocument.map { DocumentTitle.displayName(for: $0) } ?? "")
        #if !os(macOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("Page", selection: page) {
                    ForEach(ItemPage.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented)
                .accessibilityValue(page.wrappedValue.position)
            }
        }
        // Swipe up or down moves a page for VoiceOver.
        .accessibilityAdjustableAction { direction in
            let target = direction == .increment ? page.wrappedValue.next : page.wrappedValue.previous
            if let target { page.wrappedValue = target }
        }
    }

    private var compactItemPageBinding: Binding<ItemPage> {
        Binding(
            get: { windowState.compactItemPage },
            // No slide with Reduce Motion on: the page is swapped in place.
            set: { new in withAnimation(ItemPage.changeAnimation(reduceMotion: reduceMotion)) { windowState.compactItemPage = new } }
        )
    }

    @ViewBuilder
    private func compactItemPageContent(_ page: ItemPage) -> some View {
        switch page {
        case .source: previewView
        case .reader: AnyView(widescreenReadingPane())
        case .segments: SegmentsPaneView(document: previewDocument)
        case .info: AnyView(inspectorView)
        }
    }
}
