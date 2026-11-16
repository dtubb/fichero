import SwiftUI

/// The bar at the bottom of the Segments pane (`source.editor.segments-list-has-a-filter-bar`, Step 1.29, #6476): a
/// search field, a menu of facets (Kind, Reading, Flagged, Low Confidence, Language, Script, Direction) and "N of M".
/// Esc in the field clears the whole filter. The rule itself is `SegmentsFilter`; this bar only sets its values.
struct SegmentsFilterBar: View {
    @Binding var filter: SegmentsFilter
    let options: SegmentsFilter.Options
    /// How many rows match, and how many the page holds at the levels listed; nil while no filter is on.
    let count: (matched: Int, total: Int)?
    @FocusState private var fieldFocused: Bool

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "line.3.horizontal.decrease")
                .foregroundStyle(filter.isActive ? Color.accentColor : .secondary)
                .accessibilityHidden(true)
            TextField("Filter", text: $filter.query)
                .textFieldStyle(.plain)
                .focused($fieldFocused)
                .accessibilityIdentifier("segments.filter.field")
                #if os(macOS)
                .onExitCommand { filter = SegmentsFilter() }
                #endif
            if let count {
                Text(SegmentsFilter.countLine(matched: count.matched, of: count.total))
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("segments.filter.count")
            }
            facetMenu
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
    }

    private var facetMenu: some View {
        Menu {
            Section("Kind") {
                ForEach(options.kinds, id: \.self) { kind in
                    Toggle(kind.capitalized, isOn: member(kind, of: \.kinds))
                }
            }
            Section("Reading") {
                Picker("Reading", selection: $filter.reading) {
                    Text("Any").tag(SegmentsFilter.Reading?.none)
                    ForEach(SegmentsFilter.Reading.allCases) { reading in
                        Text(reading.title).tag(Optional(reading))
                    }
                }
                .pickerStyle(.inline)
                .labelsHidden()
                Toggle("Flagged", isOn: $filter.flaggedOnly)
                Toggle("Low Confidence", isOn: $filter.doubtfulOnly)
            }
            valueSection("Language", options.languages, \.languages)
            valueSection("Script", options.scripts, \.scripts)
            valueSection("Direction", options.directions, \.directions)
            Divider()
            Button("Clear Filter") { filter = SegmentsFilter() }
                .disabled(!filter.isActive)
        } label: {
            Image(systemName: "slider.horizontal.3")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter by kind, reading, language, script or direction")
        .accessibilityLabel("Filter Options")
        .accessibilityIdentifier("segments.filter.menu")
    }

    @ViewBuilder
    private func valueSection(
        _ title: String, _ values: [String], _ path: WritableKeyPath<SegmentsFilter, Set<String>>
    ) -> some View {
        if !values.isEmpty {
            Section(title) {
                ForEach(values, id: \.self) { value in
                    Toggle(value, isOn: member(value, of: path))
                }
            }
        }
    }

    /// A toggle for one value of a set facet.
    private func member(_ value: String, of path: WritableKeyPath<SegmentsFilter, Set<String>>) -> Binding<Bool> {
        Binding(
            get: { filter[keyPath: path].contains(value) },
            set: { isOn in
                if isOn { filter[keyPath: path].insert(value) } else { filter[keyPath: path].remove(value) }
            }
        )
    }
}

#Preview("Segments filter bar: on, 3 of 12") {
    @Previewable @State var filter = SegmentsFilter(query: "capilla")
    return SegmentsFilterBar(
        filter: $filter,
        options: .init(kinds: ["line", "region", "word"], languages: ["es", "la"], scripts: ["Latn"], directions: ["ltr"]),
        count: (3, 12)
    )
    .frame(width: 320)
}
