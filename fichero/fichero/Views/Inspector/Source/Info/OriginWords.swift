import Foundation

/// Where one effective value came from, as the engine's `effective-attributes` says it
/// (`proto.value.set-inherited-default-empty`): `{origin, from, source}` per key.
struct AttributeOrigin: Equatable, Sendable {
    enum Kind: String, Sendable { case here, inherited, `default`, empty }

    /// Who set the value, when the engine kept that: a person, or a machine with its model.
    struct Source: Equatable, Sendable {
        let byMachine: Bool
        let model: String?
        let name: String?
    }

    let kind: Kind
    /// The ancestor's id for `inherited`, the prototype key for `default`.
    let from: String?
    let source: Source?

    var inheritedFrom: String? { kind == .inherited ? from : nil }

    init(kind: Kind, from: String? = nil, source: Source? = nil) {
        self.kind = kind
        self.from = from
        self.source = source
    }

    /// The engine's `origins` object (`{key: {origin, from, source}}`) as JSON; a key it cannot read is left out.
    static func decodeAll(_ json: Data?) -> [String: AttributeOrigin] {
        guard let json, let top = try? JSONSerialization.jsonObject(with: json) as? [String: [String: Any]] else { return [:] }
        return top.compactMapValues { AttributeOrigin(raw: $0) }
    }

    init?(raw: [String: Any]) {
        guard let word = raw["origin"] as? String, let kind = Kind(rawValue: word) else { return nil }
        let source = (raw["source"] as? [String: Any]).map {
            Source(byMachine: $0["by"] as? String == "machine", model: $0["model"] as? String, name: $0["name"] as? String)
        }
        self.init(kind: kind, from: raw["from"] as? String, source: source)
    }
}

/// An origin in words, and whether the value is greyed. Pure: the names come in, nothing is fetched here.
enum OriginWords {
    /// "set here", "from Caja 12", "default of EAP digital folder", "Fichero (<model>)"; nil for an empty value.
    static func words(
        _ origin: AttributeOrigin, ancestorNames: [String: String], prototypeLabels: [String: String]
    ) -> String? {
        switch origin.kind {
        case .empty:
            return nil
        case .here:
            return setBy(origin.source) ?? "set here"
        case .inherited:
            let name = origin.from.flatMap { ancestorNames[$0] }
            return name.map { "from \($0)" } ?? "from an ancestor"
        case .default:
            let label = origin.from.flatMap { prototypeLabels[$0] ?? $0 }
            return label.map { "default of \($0)" } ?? "default"
        }
    }

    /// A value another node or the prototype gave is greyed; only a value set here is plain.
    static func isGreyed(_ origin: AttributeOrigin?) -> Bool {
        guard let origin else { return false }
        return origin.kind == .inherited || origin.kind == .default
    }

    /// The kind row: "own" for a kind set here, "from <ancestor>'s kind" for an inherited one.
    static func kindWords(rule: String, from: String?, ancestorNames: [String: String]) -> String? {
        switch rule {
        case "own": return "set here"
        case "inherited": return from.flatMap { ancestorNames[$0] }.map { "from \($0)’s kind" } ?? "from an ancestor’s kind"
        default: return nil
        }
    }

    private static func setBy(_ source: AttributeOrigin.Source?) -> String? {
        guard let source else { return nil }
        if source.byMachine { return source.model.map { "Fichero (\($0))" } ?? "Fichero" }
        return source.name
    }
}
