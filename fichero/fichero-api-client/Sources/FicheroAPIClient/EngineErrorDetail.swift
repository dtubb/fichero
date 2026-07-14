import Foundation
import OpenAPIRuntime

// FastAPI error bodies, hoisted to file scope so no type nests more than one level
// deep. `detail` is usually a string, but a 422 validation error makes it an array of
// {loc, msg, type}. Decode either shape.

/// A `loc` entry mixes strings ("body", field names) and array indices (ints).
private enum FastAPILocComponent: Decodable {
    case string(String)
    case index(Int)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self) {
            self = .string(text)
        } else {
            self = .index(try container.decode(Int.self))
        }
    }

    var text: String {
        switch self {
        case .string(let value): return value
        case .index(let value): return String(value)
        }
    }
}

private struct FastAPIValidationItem: Decodable {
    let loc: [FastAPILocComponent]?
    let msg: String?
}

private enum FastAPIDetail: Decodable {
    case message(String)
    case validation([FastAPIValidationItem])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self) {
            self = .message(text)
        } else {
            self = .validation(try container.decode([FastAPIValidationItem].self))
        }
    }
}

private struct FastAPIErrorEnvelope: Decodable {
    let detail: FastAPIDetail?
}

/// Extracts the engine's error message from a FastAPI response body (#3802).
///
/// Every FastAPI `HTTPException` serialises as `{"detail": "<message>"}`. The app
/// used to throw that body away and render a generic string, so a workflow that 400'd
/// with `{"detail": "Workflow validation failed: X"}` showed only
/// "Server error (400): Execute workflow failed" — the actual reason gone.
///
/// This is the ONE place that turns such a body into a string, so the fix is uniform
/// across every endpoint rather than re-implemented per service. It is intentionally
/// forgiving: a body that is missing, empty, non-JSON, or shaped differently yields
/// nil, and the caller falls back to its generic message. A malformed error body must
/// never turn into a crash or a misleading detail.
public enum EngineErrorDetail {

    /// The engine's message from a raw body, or nil if there is nothing usable.
    public static func message(from data: Data?) -> String? {
        guard let data, !data.isEmpty,
              let envelope = try? JSONDecoder().decode(FastAPIErrorEnvelope.self, from: data),
              let detail = envelope.detail else {
            return nil
        }
        switch detail {
        case .message(let text):
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        case .validation(let items):
            // "field: reason" per entry, so a 422 reads like a sentence rather than a
            // JSON dump. Drop the leading "body" that FastAPI prepends to every loc.
            let lines = items.compactMap { item -> String? in
                guard let msg = item.msg, !msg.isEmpty else { return nil }
                let field = (item.loc ?? [])
                    .map(\.text)
                    .filter { $0 != "body" }
                    .joined(separator: ".")
                return field.isEmpty ? msg : "\(field): \(msg)"
            }
            return lines.isEmpty ? nil : lines.joined(separator: "; ")
        }
    }

    /// Collect an OpenAPI `UndocumentedPayload` body and pull the detail out of it.
    /// The generated client surfaces a non-2xx as `.undocumented(statusCode, payload)`;
    /// its body is where the engine's message lives. Bounded so a hostile/huge error
    /// body cannot be read without limit.
    public static func message(
        from payload: UndocumentedPayload,
        upTo maxBytes: Int = 64 * 1024
    ) async -> String? {
        guard let body = payload.body else { return nil }
        guard let data = try? await Data(collecting: body, upTo: maxBytes) else { return nil }
        return message(from: data)
    }
}
