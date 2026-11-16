import FicheroAPIClient
import SwiftUI

/// The log's lines as Xcode draws them (`activity.log.like-xcode`, decision 36, #6588): a find bar, then one row per line
/// with its number, level glyph, time and text, monospaced. A click selects a line, shift extends, command adds or removes;
/// ⌘C and Copy copy the selected lines, or all of them. Inside the Inspector's one scroll view (`activity.window.open-a-run`).
struct ActivityLogLinesView: View {
    let lines: [ActivityJobLogLine]
    @Binding var selection: ActivityLogList.Selection
    @State private var query = ""
    @State private var current = 0

    private var found: [Int] { ActivityLogList.matches(lines, query: query) }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            findBar
            ScrollViewReader { proxy in
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(lines) { line in
                        row(line)
                            .id(line.id)
                    }
                }
                .onChange(of: current) { _, index in scroll(proxy, to: index) }
                .onChange(of: query) { _, _ in current = 0; scroll(proxy, to: 0) }
            }
            .font(.callout.monospaced())
            #if os(macOS)
            .onCopyCommand {
                [NSItemProvider(object: ActivityLogList.copyText(lines, selected: selection.lines) as NSString)]
            }
            #endif
        }
        .accessibilityIdentifier("activity.details.log.lines")
    }

    private var findBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
            TextField("Find in log", text: $query)
                .textFieldStyle(.plain)
                .onSubmit { current = ActivityLogList.step(current, of: found.count, forward: true) }
                .accessibilityIdentifier("activity.details.log.find")
            if !query.trimmingCharacters(in: .whitespaces).isEmpty {
                Text(ActivityLogList.matchWords(current: current, of: found.count))
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                Button { current = ActivityLogList.step(current, of: found.count, forward: false) } label: {
                    Label("Previous Match", systemImage: "chevron.up")
                }
                .disabled(found.isEmpty)
                Button { current = ActivityLogList.step(current, of: found.count, forward: true) } label: {
                    Label("Next Match", systemImage: "chevron.down")
                }
                .disabled(found.isEmpty)
            }
        }
        .labelStyle(.iconOnly).buttonStyle(.borderless).controlSize(.small)
        .padding(.horizontal, 6).padding(.vertical, 3)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
    }

    private func row(_ line: ActivityJobLogLine) -> some View {
        let glyph = ActivityLogList.glyph(line.level)
        let selected = selection.lines.contains(line.id)
        let isCurrent = found.indices.contains(current) && found[current] == line.id
        return HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text("\(line.id + 1)")
                .foregroundStyle(.tertiary)
                .frame(minWidth: 28, alignment: .trailing)
            Image(systemName: glyph.symbol).foregroundStyle(glyph.color).font(.caption)
            Text(line.timestamp.map { $0.formatted(date: .omitted, time: .standard) } ?? "now")
                .foregroundStyle(.secondary)
            Text(ActivityLogList.highlighted(line.message, query: query))
                .foregroundStyle(line.level == "error" ? AnyShapeStyle(.red) : AnyShapeStyle(.primary))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 1).padding(.horizontal, 2)
        .background(selected ? AnyShapeStyle(Color.accentColor.opacity(0.22))
                    : isCurrent ? AnyShapeStyle(Color.yellow.opacity(0.18)) : AnyShapeStyle(Color.clear))
        .contentShape(Rectangle())
        .gesture(
            TapGesture().modifiers(.command).onEnded { selection.click(line.id, shift: false, command: true) }
                .exclusively(before: TapGesture().modifiers(.shift).onEnded { selection.click(line.id, shift: true, command: false) })
                .exclusively(before: TapGesture().onEnded { selection.click(line.id, shift: false, command: false) })
        )
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func scroll(_ proxy: ScrollViewProxy, to index: Int) {
        guard found.indices.contains(index) else { return }
        withAnimation { proxy.scrollTo(found[index], anchor: .center) }
    }
}

#Preview("The log, Xcode style") {
    @Previewable @State var selection = ActivityLogList.Selection()
    let json = """
    [{"timestamp": "2026-11-15T14:05:01+00:00", "level": "info", "message": "Reading page 1 with Kraken (catmus)", "job_id": "j"},
     {"timestamp": "2026-11-15T14:05:03+00:00", "level": "warning", "message": "Page 2 is faint: 41 lines found", "job_id": "j"},
     {"timestamp": "2026-11-15T14:05:04+00:00", "level": "error", "message": "Failed: page 3 could not be read", "job_id": "j"},
     {"timestamp": "2026-11-15T14:05:09+00:00", "level": "debug", "message": "page 3 retried on the lane", "job_id": "j"},
     {"timestamp": "2026-11-15T14:05:12+00:00", "level": "info", "message": "Page 3 read: 38 lines", "job_id": "j"}]
    """
    let decoded = (try? JSONDecoder().decode([Components.Schemas.JobLogLine].self, from: Data(json.utf8))) ?? []
    let lines = decoded.enumerated().map { ActivityJobLogLine(index: $0.offset, $0.element) }
    ScrollView {
        ActivityLogLinesView(lines: lines, selection: $selection).padding()
    }
    .frame(width: 560, height: 220)
}
