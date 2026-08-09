import SwiftUI

extension DocumentInspector {
    /// The four-section top icon row — the approved IA switcher (#3434, top icon
    /// row chosen 2026-07-11): Source / Artifacts / Knowledge / Notes. One
    /// grouped capsule with a selected-segment fill, reading as ONE control.
    /// Stays icon-only buttons (not a `.segmented` Picker) so per-section `.help`
    /// tooltips and `.accessibilityIdentifier` XCUITest hooks attach per segment.
    /// Multi-facet sections reveal a sub-picker below (see ``facetPicker``).
    /// The shared `SurfaceTabBar` (#3530) — the same icon-button row the Reader
    /// uses — over the document's available sections. Per-section help + XCUITest
    /// hooks (`inspectorSection-Source`, …) and the container `inspectorSectionBar`
    /// hook are preserved via `InspectorSection: SurfaceTab` + the container id.
    var sectionBar: some View {
        SurfaceTabBar(
            tabs: availableSections(for: document),
            selection: sectionSelectionBinding,
            accessibilityID: "inspectorSectionBar"
        )
    }

    /// Active section ↔ selected facet: reads the section the current tab belongs
    /// to; selecting a section switches to its first facet (unchanged behaviour).
    private var sectionSelectionBinding: Binding<InspectorSection> {
        Binding(
            get: { Self.section(for: selectedTab, in: document) },
            set: { selectSection($0) }
        )
    }

    /// Sub-facet selector shown only when the active section absorbs more than
    /// one legacy facet (Knowledge = entities/graph/citations; Notes =
    /// notes/annotations/interpretation). A native segmented picker over the
    /// section's facets — each facet body is reused unchanged (iterate, not
    /// replace). Single-facet sections (Artifacts) show nothing here.
    @ViewBuilder
    func facetPicker(for doc: Document, selectedTab tab: InspectorTab) -> some View {
        let section = Self.section(for: tab, in: doc)
        let facets = facets(in: section, for: doc)
        if facets.count > 1 {
            // Width-adaptive (Daniel, 2026-08-09: "the tabs of the document
            // inspector knowledge tabs are too long so that if the inspector
            // is too narrow they're cut off"): full labels when they fit,
            // otherwise Xcode's degrade-to-icons — never clipped text. The
            // icon variant keeps the labels reachable via per-segment .help.
            ViewThatFits(in: .horizontal) {
                facetSegments(facets, iconOnly: false)
                facetSegments(facets, iconOnly: true)
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 6)
            .accessibilityIdentifier("inspectorFacetPicker")
        }
    }

    /// One segmented facet picker, in label or icon form. Icons come from the
    /// same InspectorTab.icon ladder the section bar reads.
    private func facetSegments(_ facets: [InspectorTab], iconOnly: Bool) -> some View {
        Picker("Facet", selection: facetSelection) {
            ForEach(facets) { facet in
                if iconOnly {
                    Image(systemName: facet.icon)
                        .help(facet.rawValue)
                        .accessibilityLabel(facet.rawValue)
                        .tag(facet)
                } else {
                    Text(facet.rawValue).tag(facet)
                }
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
    }

    private var facetSelection: Binding<InspectorTab> {
        Binding(
            get: { Self.clampedSelectedTab(selectedTab, for: document) },
            set: { selectTab($0) }
        )
    }

    /// The section for a facet, clamped to something valid for this document.
    static func section(for tab: InspectorTab, in doc: Document?) -> InspectorSection {
        InspectorSection.section(for: clampedSelectedTab(tab, for: doc)) ?? .source
    }

    /// The legacy facets of `section` that are available for this document.
    private func facets(in section: InspectorSection, for doc: Document?) -> [InspectorTab] {
        let available = Set(Self.availableTabs(for: doc))
        return section.facets.filter { available.contains($0) }
    }

    private func availableSections(for doc: Document?) -> [InspectorSection] {
        InspectorSection.allCases.filter { !facets(in: $0, for: doc).isEmpty }
    }

    /// Switch top section: jump to its first facet unless already inside it.
    private func selectSection(_ section: InspectorSection) {
        guard Self.section(for: selectedTab, in: document) != section else { return }
        if let first = facets(in: section, for: document).first {
            selectTab(first)
        }
    }

    /// Switch the inspector tab, first persisting any in-flight Page Content
    /// edit so it isn't lost when the Content tab's editor disappears (#2476).
    /// Only defers when an editor is registered, so tab switching stays snappy.
    private func selectTab(_ tab: InspectorTab) {
        if documentStore.activePageEditFlush != nil {
            Task { @MainActor in
                await documentStore.flushActivePageEdit()
                selectedTab = tab
            }
        } else {
            selectedTab = tab
        }
    }

    static func clampedSelectedTab(_ selectedTab: InspectorTab, for doc: Document?) -> InspectorTab {
        let tabs = availableTabs(for: doc)
        return tabs.contains(selectedTab) ? selectedTab : .content
    }

    private static func availableTabs(for doc: Document?) -> [InspectorTab] {
        guard let doc else { return InspectorTab.allCases }
        var tabs: [InspectorTab] = [
            .content, .artifacts, .annotations, .notes, .interpretations, .knowledgeGraph,
            .entities, .citations, .related
        ]
        // Image/page edit CONTROLS live in the Inspector, Lightroom-style (#3593,
        // 2026-07-12 — this reverses #3434's "edits left the inspector":
        // the controls belong here, the Preview is the live canvas). Only for the
        // surfaces the editor supports (images and PDF/scanned pages).
        if doc.fileType == .image || doc.fileType == .pdf || doc.docType == .page {
            tabs.append(.edits)
        }
        // Info is no longer a standalone tab — it is folded into the Source body's
        // Content/Info/Outline picker (SourceSectionMode, #3876). Not appending it
        // here means a persisted `.info` selection clamps to `.content` (Source)
        // instead of stranding on the old full-screen Info view with no picker.
        return tabs
    }
}
