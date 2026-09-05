// fm-bridge — minimal CLI wrapper around Foundation Models.
//
// Reads a JSON request from stdin, runs an Apple Intelligence LLM call
// via FoundationModels.LanguageModelSession, writes a JSON response to
// stdout. Exits non-zero on errors with a JSON error payload on stderr.
//
// This bridge exists because FoundationModels' public API is Swift-native
// and not @objc-exposed, so pyobjc can load the classes but can't call
// `respond(to:)`. Python's `chat()` subprocesses this binary instead.
//
// Build (dev): swiftc -O -parse-as-library -o fm-bridge main.swift
// Build (universal release): see scripts/build_fm_bridge.sh
//
// Free-form request (stdin):
//   {"prompt": "...", "instructions": "..." (optional),
//    "temperature": 0.7 (optional), "max_tokens": 2048 (optional)}
//
// Free-form response (stdout):
//   {"response": "...", "model": "apple-intelligence"}
//
// Structured request (stdin) — adds "schema" to free-form fields:
//   {"prompt": "...", "instructions": "...", "schema": <schema-tree>,
//    "include_schema_in_prompt": true (default; set false when our
//    own instructions already describe the shape, saving prompt tokens)}
//
// Structured response (stdout):
//   {"response_json": "<raw json string from grammar-constrained output>",
//    "model": "apple-intelligence"}
//
// Error kinds (stderr):
//   - "unavailable"        Apple Intelligence not available on device
//   - "json"               Bad request payload
//   - "schema"             Schema tree malformed or rejected by FoundationModels
//   - "guardrail"          Safety filter refused prompt or response
//   - "refusal"            Model declined the request (only on guided generation)
//   - "decoding"           Generation truncated mid-output (bump max_tokens)
//   - "context_overflow"   Prompt+schema exceed context window — chunk smaller
//   - "rate_limited"       Session is rate-limited; back off and retry
//   - "concurrent"         Concurrent request on same session (should not happen
//                          via subprocess; included for completeness)
//   - "unsupported_guide"  Schema uses a guide pattern the model doesn't support
//   - "unsupported_language" Prompt language isn't supported by the model
//   - "assets"             Model assets unavailable (e.g. Apple Intelligence
//                          off or assets evicted)
//   - "generation"         Anything else from the model
//
// Schema tree shape (#799/#819) — minimal subset of JSON-Schema mapped
// onto FoundationModels.DynamicGenerationSchema. Recursive:
//
//   {"type": "object", "name": "Extraction",
//    "properties": [
//      {"name": "people", "schema": {"type": "array", "items": {...}}},
//      {"name": "dates",  "schema": {"type": "array", "items": {...}}, "optional": true}
//    ]}
//   {"type": "array", "items": {<schema>}, "minimum_elements": 0,
//    "maximum_elements": 50}
//   {"type": "string"}      // primitive
//   {"type": "integer"}     // primitive
//   {"type": "number"}      // primitive
//   {"type": "boolean"}     // primitive
//
// Error shape (stderr, on failure):
//   {"error": "...", "kind": "unavailable|generation|json|schema"}

import Foundation
import FoundationModels
import Translation
// Vision joins for --recognize-documents. fm-bridge is not "the Foundation
// Models binary", it is the Swift side of frameworks the Python engine cannot
// call (lane-model-routing, 2026-09-04) — a sibling binary would mean a second
// build, a second staging step, a second thing to notarize, and a second path
// for the engine to fail to find. System framework, dynamically linked, loaded
// lazily: the Apple Intelligence and Translation paths pay nothing for it.
import Vision

struct SuccessResponse: Codable {
    let response: String
    let model: String
}

struct StructuredSuccessResponse: Codable {
    let response_json: String
    let model: String
}

struct ErrorResponse: Codable {
    let error: String
    let kind: String
}

func emitError(_ message: String, kind: String) -> Never {
    let err = ErrorResponse(error: message, kind: kind)
    if let data = try? JSONEncoder().encode(err) {
        FileHandle.standardError.write(data)
    }
    exit(1)
}

/// Emit a probe result `{"available": Bool, "reason": String?}` to stdout
/// and exit. Used by `--probe` mode for the onboarding wizard's "Is Apple
/// Intelligence available on this Mac?" check, so we don't have to spin up
/// a real generation to find out.
struct ProbeResponse: Codable {
    let available: Bool
    let reason: String?
}

func emitProbe(available: Bool, reason: String?) -> Never {
    let payload = ProbeResponse(available: available, reason: reason)
    if let data = try? JSONEncoder().encode(payload) {
        FileHandle.standardOutput.write(data)
    }
    exit(available ? 0 : 1)
}

// MARK: - Schema construction

/// Recursively convert a JSON-Schema-shaped dict into a
/// DynamicGenerationSchema. Caller is responsible for the dict shape;
/// see top-of-file comment for the supported subset.
func buildDynamicSchema(_ json: [String: Any]) throws -> DynamicGenerationSchema {
    let type = (json["type"] as? String) ?? "object"
    let name = json["name"] as? String
    let description = json["description"] as? String

    switch type {
    case "object":
        let propsJson = (json["properties"] as? [[String: Any]]) ?? []
        var props: [DynamicGenerationSchema.Property] = []
        for p in propsJson {
            guard let pname = p["name"] as? String, !pname.isEmpty else {
                throw SchemaError.missingPropertyName
            }
            let pdesc = p["description"] as? String
            let pIsOptional = (p["optional"] as? Bool) ?? false
            let pSchemaDict: [String: Any]
            if let inline = p["schema"] as? [String: Any] {
                pSchemaDict = inline
            } else {
                // Allow shorthand where the property dict IS the schema
                // (e.g. {"name": "score", "type": "number"}).
                var copy = p
                copy.removeValue(forKey: "name")
                copy.removeValue(forKey: "description")
                copy.removeValue(forKey: "optional")
                pSchemaDict = copy
            }
            let pSchema = try buildDynamicSchema(pSchemaDict)
            props.append(
                DynamicGenerationSchema.Property(
                    name: pname,
                    description: pdesc,
                    schema: pSchema,
                    isOptional: pIsOptional
                )
            )
        }
        return DynamicGenerationSchema(
            name: name ?? "Object",
            description: description,
            properties: props
        )

    case "array":
        guard let itemsDict = json["items"] as? [String: Any] else {
            throw SchemaError.arrayMissingItems
        }
        let element = try buildDynamicSchema(itemsDict)
        let minE = json["minimum_elements"] as? Int
        let maxE = json["maximum_elements"] as? Int
        return DynamicGenerationSchema(
            arrayOf: element,
            minimumElements: minE,
            maximumElements: maxE
        )

    case "string":
        return DynamicGenerationSchema(type: String.self, guides: [])
    case "integer":
        return DynamicGenerationSchema(type: Int.self, guides: [])
    case "number":
        return DynamicGenerationSchema(type: Double.self, guides: [])
    case "boolean":
        return DynamicGenerationSchema(type: Bool.self, guides: [])

    default:
        throw SchemaError.unsupportedType(type)
    }
}

/// Map a thrown error from session.respond(...) to (errorKind, message)
/// using the typed `GenerationError` enum cases. Falls back to "generation"
/// for unknown errors. Replaces fragile string-matching in Python (#843).
func classifyGenerationError(_ error: Error) -> (kind: String, message: String) {
    if let gen = error as? LanguageModelSession.GenerationError {
        switch gen {
        case .guardrailViolation:
            return ("guardrail", "Apple Intelligence safety guardrail refused the request: \(gen.localizedDescription)")
        case .refusal(let refusal, _):
            // Refusal is the model itself declining (only on guided
            // generation). Surface its explanation when available so
            // the user knows why.
            return ("refusal", "Model declined the request: \(refusal)")
        case .decodingFailure:
            return ("decoding", "Apple Intelligence terminated generation early before producing valid output: \(gen.localizedDescription)")
        case .exceededContextWindowSize:
            return ("context_overflow", "Prompt + schema exceeds Apple Intelligence's context window: \(gen.localizedDescription)")
        case .rateLimited:
            return ("rate_limited", "Apple Intelligence session is rate-limited: \(gen.localizedDescription)")
        case .concurrentRequests:
            return ("concurrent", "Concurrent request on same Apple Intelligence session: \(gen.localizedDescription)")
        case .unsupportedGuide:
            return ("unsupported_guide", "Schema uses a generation guide pattern the on-device model doesn't support: \(gen.localizedDescription)")
        case .unsupportedLanguageOrLocale:
            return ("unsupported_language", "Apple Intelligence does not support the prompt's language/locale: \(gen.localizedDescription)")
        case .assetsUnavailable:
            return ("assets", "Apple Intelligence model assets are unavailable: \(gen.localizedDescription)")
        @unknown default:
            return ("generation", "Apple Intelligence generation error: \(gen.localizedDescription)")
        }
    }
    return ("generation", "Generation failed: \(error)")
}

enum SchemaError: Error, CustomStringConvertible {
    case missingPropertyName
    case arrayMissingItems
    case unsupportedType(String)

    var description: String {
        switch self {
        case .missingPropertyName:
            return "object property is missing 'name'"
        case .arrayMissingItems:
            return "array schema is missing 'items'"
        case .unsupportedType(let t):
            return "unsupported schema type '\(t)' (expected object|array|string|integer|number|boolean)"
        }
    }
}

/// Validate the incoming schema-tree payload before we build
/// DynamicGenerationSchema. This gives callers clearer diagnostics for
/// malformed trees (missing required keys, wrong primitive types) rather
/// than a generic GenerationSchema init failure.
func validateSchemaTree(_ json: [String: Any], path: String = "$") throws {
    let type = (json["type"] as? String) ?? "object"

    switch type {
    case "object":
        guard let properties = json["properties"] as? [[String: Any]] else {
            throw SchemaError.unsupportedType(
                "\(path): object missing 'properties' array"
            )
        }
        for (idx, prop) in properties.enumerated() {
            guard let name = prop["name"] as? String, !name.isEmpty else {
                throw SchemaError.unsupportedType(
                    "\(path).properties[\(idx)]: missing non-empty 'name'"
                )
            }
            if let nested = prop["schema"] as? [String: Any] {
                try validateSchemaTree(nested, path: "\(path).\(name)")
            } else {
                var inline = prop
                inline.removeValue(forKey: "name")
                inline.removeValue(forKey: "description")
                inline.removeValue(forKey: "optional")
                try validateSchemaTree(inline, path: "\(path).\(name)")
            }
        }
    case "array":
        guard let items = json["items"] as? [String: Any] else {
            throw SchemaError.unsupportedType("\(path): array missing 'items'")
        }
        try validateSchemaTree(items, path: "\(path)[]")
    case "string", "integer", "number", "boolean":
        break
    default:
        throw SchemaError.unsupportedType(
            "\(path): unsupported type '\(type)' (expected object|array|string|integer|number|boolean)"
        )
    }
}

/// Locale-support response shape for `--supports-locale <code>` (#849).
struct LocaleSupportResponse: Codable {
    let locale: String
    let supported: Bool
}


// =============================================================================
// Translation (`--translate`) — Apple's free on-device translator.
//
// A SEPARATE framework from FoundationModels: it needs no Apple Intelligence,
// no model assets, and works on machines where the LLM path is unavailable.
// So it dispatches BEFORE this bridge's Apple Intelligence availability
// check, the way --probe and --supports-locale already do.
//
// Request (stdin):
//   {"source": "es", "target": "en", "texts": ["…", "…"]}
//
// Response (stdout):
//   {"source_language": "es", "target_language": "en",
//    "translations": ["…", "…"], "model": "apple-translation"}
//
// `source` is REQUIRED. TranslationSession's headless initializer
// (`installedSource:target:`) takes a concrete source language, and the
// engine already knows the document's language (llm/lang_detect.py) — asking
// the caller for the answer it already has beats guessing here.
//
// Error kinds (stderr), on top of the shared "json":
//   - "not_installed"     the pair is supported but not downloaded. NAMES the
//                         pair. Downloading needs the UI (a translationTask
//                         presenting Apple's own sheet), which a CLI has no
//                         way to show — so this refuses instead of silently
//                         returning the source text as though it were a
//                         translation.
//   - "unsupported_pair"  Apple does not translate between these languages.
//   - "translation"       anything else the framework raised.
// =============================================================================

struct TranslateSuccessResponse: Codable {
    let source_language: String
    let target_language: String
    let translations: [String]
    let model: String
}

/// Read the translate request, or exit with a "json" error naming what is
/// missing. Split out so the shape of a valid request is stated in one place.
func parseTranslateRequest(
    _ raw: [String: Any]
) -> (source: String, target: String, texts: [String]) {
    guard let source = (raw["source"] as? String)?.trimmingCharacters(in: .whitespaces),
          !source.isEmpty
    else {
        emitError(
            "Missing 'source' language. The headless translator needs a concrete "
            + "source language; detect it before calling.",
            kind: "json"
        )
    }
    guard let target = (raw["target"] as? String)?.trimmingCharacters(in: .whitespaces),
          !target.isEmpty
    else {
        emitError("Missing 'target' language", kind: "json")
    }
    guard let texts = raw["texts"] as? [String], !texts.isEmpty else {
        emitError("Missing or empty 'texts' array", kind: "json")
    }
    return (source, target, texts)
}

@available(macOS 26.0, *)
func runTranslate(_ raw: [String: Any]) async {
    let request = parseTranslateRequest(raw)
    let source = Locale.Language(identifier: request.source)
    let target = Locale.Language(identifier: request.target)

    // Ask BEFORE translating. A pair that is merely `.supported` has no model
    // on disk, and the framework's own error for that case does not say which
    // pair to download — the caller cannot act on "internalError".
    switch await LanguageAvailability().status(from: source, to: target) {
    case .installed:
        break
    case .supported:
        emitError(
            "The \(request.source) → \(request.target) translation model is not "
            + "downloaded on this Mac. Open Fichero and run the translation once "
            + "so macOS can offer the download, or install it in System Settings › "
            + "General › Language & Region › Translation Languages.",
            kind: "not_installed"
        )
    case .unsupported:
        emitError(
            "macOS does not translate \(request.source) → \(request.target).",
            kind: "unsupported_pair"
        )
    @unknown default:
        emitError(
            "Unknown translation availability for \(request.source) → "
            + "\(request.target).",
            kind: "translation"
        )
    }

    let session = TranslationSession(installedSource: source, target: target)
    do {
        // `translations(from:)` returns the whole array in one call, and the
        // framework keeps the order of the requests it was given. The
        // clientIdentifier is the index so a future streaming variant can
        // still reassemble; nothing here depends on it.
        let responses = try await session.translations(
            from: request.texts.enumerated().map { index, text in
                TranslationSession.Request(sourceText: text, clientIdentifier: "\(index)")
            }
        )
        let payload = TranslateSuccessResponse(
            source_language: request.source,
            target_language: request.target,
            translations: responses.map(\.targetText),
            model: "apple-translation"
        )
        FileHandle.standardOutput.write(try JSONEncoder().encode(payload))
    } catch {
        emitError("Translation failed: \(error)", kind: "translation")
    }
}

// MARK: - Document recognition (Vision, macOS 26+)

struct RecognizedRegion: Codable {
    let index: Int
    let text: String
    /// Normalized 0..1, TOP-LEFT origin, flipped here at the boundary — the
    /// same place `_vision_flip_bbox_to_top_left` flips on the Python side.
    /// A flip deferred to the consumer is a half-page offset that reads as a
    /// bad model rather than a bad convention.
    let polygon: [[Double]]
    let bbox: [Double]
}

/// The warm-up answers a DIFFERENT question from --probe, so it gets its own
/// shape. Reusing ProbeResponse made `available` mean "Apple Intelligence is
/// usable" in one subcommand and "the warm-up completed" in another — one
/// field, two meanings, one binary (lane-model-routing review, 2026-09-04).
struct WarmDocumentsResponse: Codable {
    let warmed: Bool
    /// Reported because the falsifiable prediction depends on it: on a COLD
    /// machine this should itself take ~45s, since it is paying the one-time
    /// cost. A prediction the caller cannot see is a prediction nobody checks.
    let elapsed_ms: Int
    let reason: String?
}

struct RecognizeDocumentsResponse: Codable {
    let engine: String
    /// WHICH PICTURE these fractions describe. Vision normalizes against the
    /// image it was handed, so a result that does not name its frame cannot be
    /// placed on a page that has more than one rendition.
    let pixel_frame: [String: Int]
    /// Elapsed time, because a 168s cold start and a 0.7s warm call on the same
    /// page are indistinguishable to the caller otherwise — this is how Python
    /// tells "cold" from "something is wrong".
    let elapsed_ms: Int
    let line_count: Int
    let word_count: Int
    let lines: [RecognizedRegion]
    let words: [RecognizedRegion]
}

func flippedPolygon(_ points: [simd_float2]) -> [[Double]] {
    points.map { [Double($0.x), 1.0 - Double($0.y)] }
}

func polygonBBox(_ polygon: [[Double]]) -> [Double] {
    guard let first = polygon.first else { return [0, 0, 0, 0] }
    var minX = first[0], maxX = first[0], minY = first[1], maxY = first[1]
    for point in polygon {
        minX = min(minX, point[0]); maxX = max(maxX, point[0])
        minY = min(minY, point[1]); maxY = max(maxY, point[1])
    }
    return [minX, minY, maxX - minX, maxY - minY]
}

@available(macOS 26.0, *)
func recognizedRegion(_ observation: RecognizedTextObservation, index: Int) -> RecognizedRegion {
    let polygon = flippedPolygon(observation.boundingRegion.normalizedPoints)
    return RecognizedRegion(
        index: index,
        text: String(observation.transcript),
        polygon: polygon,
        bbox: polygonBBox(polygon)
    )
}

func pixelSize(ofImageAt path: String) -> (Int, Int)? {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int,
          let height = properties[kCGImagePropertyPixelHeight] as? Int
    else { return nil }
    return (width, height)
}

@available(macOS 26.0, *)
func runRecognizeDocuments(_ payload: [String: Any]) async {
    guard let path = payload["image_path"] as? String, !path.isEmpty else {
        emitError("Missing 'image_path' in request payload", kind: "json")
    }
    guard FileManager.default.isReadableFile(atPath: path) else {
        emitError("Image not found or unreadable: \(path)", kind: "not_found")
    }
    guard let (width, height) = pixelSize(ofImageAt: path) else {
        emitError("Could not read image dimensions: \(path)", kind: "not_found")
    }

    let began = Date()
    var lines: [RecognizedRegion] = []
    var words: [RecognizedRegion] = []
    do {
        let request = RecognizeDocumentsRequest()
        let observations = try await request.perform(on: URL(fileURLWithPath: path))
        for observation in observations {
            let text = observation.document.text
            for (index, line) in text.lines.enumerated() {
                lines.append(recognizedRegion(line, index: index))
            }
            for (index, word) in (text.words ?? []).enumerated() {
                words.append(recognizedRegion(word, index: index))
            }
        }
    } catch {
        // Never an empty result where a failure occurred: a page with no text
        // and a page that failed must not look alike.
        emitError("Document recognition failed: \(error)", kind: "vision")
    }

    let response = RecognizeDocumentsResponse(
        engine: "vision-recognize-documents",
        pixel_frame: ["width": width, "height": height],
        elapsed_ms: Int(Date().timeIntervalSince(began) * 1000),
        line_count: lines.count,
        word_count: words.count,
        lines: lines,
        words: words
    )
    // Encode failure must NOT exit 0 with empty stdout: silence that looks
    // like a clean run is requirement 4 inverted at the last line of the
    // function.
    do {
        FileHandle.standardOutput.write(try JSONEncoder().encode(response))
    } catch {
        emitError("Could not encode recognition result: \(error)", kind: "vision")
    }
}

/// Pay the one-time, system-wide Vision warm-up somewhere nobody is waiting on
/// a page. Measured cold: 168s on a 929x1346 scan, 45s on a blank image; warm:
/// ~0.3s. Fire-and-forget from the caller, never awaited on the engine boot
/// path, and never fatal — a warm-up that fails is a slow first page, not a
/// dead engine.
///
/// It warms through a temporary FILE, not an in-memory CGImage, because those
/// are different code paths and only the file one is what recognition uses.
/// Measured 2026-09-04: a CGImage warm-up returned success and left the next
/// real page paying 48.6s anyway. A warm-up that does not warm the path in
/// question is worse than none — it reports success and changes nothing.
@available(macOS 26.0, *)
func runWarmDocuments() async {
    let began = Date()
    var succeeded = false
    let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("fm-bridge-warm-\(UUID().uuidString).png")
    defer { try? FileManager.default.removeItem(at: url) }

    let colorSpace = CGColorSpaceCreateDeviceGray()
    if let context = CGContext(
        data: nil, width: 64, height: 64, bitsPerComponent: 8, bytesPerRow: 64,
        space: colorSpace, bitmapInfo: CGImageAlphaInfo.none.rawValue
    ) {
        context.setFillColor(gray: 1.0, alpha: 1.0)
        context.fill(CGRect(x: 0, y: 0, width: 64, height: 64))
        if let cgImage = context.makeImage(),
           let destination = CGImageDestinationCreateWithURL(
               url as CFURL, "public.png" as CFString, 1, nil
           ) {
            CGImageDestinationAddImage(destination, cgImage, nil)
            if CGImageDestinationFinalize(destination) {
                let request = RecognizeDocumentsRequest()
                succeeded = ((try? await request.perform(on: url)) != nil)
            }
        }
    }

    let response = WarmDocumentsResponse(
        warmed: succeeded,
        elapsed_ms: Int(Date().timeIntervalSince(began) * 1000),
        reason: succeeded ? nil : "Vision warm-up did not complete; the first real page will pay the cost."
    )
    // RETURN, never exit(): Swift `defer` does not run when the process is
    // terminated by exit(), so exiting here would leak the temp PNG on every
    // engine start and the defer above would make the leak invisible to the
    // next reader (lane-model-routing review, 2026-09-04).
    //
    // A failed warm-up still must not fail engine startup, so this reports
    // warmed:false and returns normally rather than erroring.
    do {
        FileHandle.standardOutput.write(try JSONEncoder().encode(response))
    } catch {
        FileHandle.standardError.write(Data("warm-up encode failed: \(error)\n".utf8))
    }
}

@main
struct FmBridge {
    static func main() async {
        let args = CommandLine.arguments

        // Translation mode — a DIFFERENT framework, dispatched before the
        // Apple Intelligence check below: on-device translation needs no LLM
        // assets and works on machines where Apple Intelligence is off.
        if args.contains("--translate") {
            let inputData = FileHandle.standardInput.readDataToEndOfFile()
            guard !inputData.isEmpty else {
                emitError("Empty stdin", kind: "json")
            }
            guard let dict = try? JSONSerialization.jsonObject(with: inputData)
                    as? [String: Any]
            else {
                emitError("Stdin JSON is not an object", kind: "json")
            }
            if #available(macOS 26.0, *) {
                await runTranslate(dict)
            } else {
                emitError(
                    "On-device translation requires macOS 26 or later.",
                    kind: "unavailable"
                )
            }
            return
        }

        // Document recognition — Vision, not Foundation Models. Dispatched
        // beside --translate and before the Apple Intelligence check for the
        // same reason: it must work on machines with Apple Intelligence off.
        if args.contains("--recognize-documents") {
            let inputData = FileHandle.standardInput.readDataToEndOfFile()
            guard !inputData.isEmpty else {
                emitError("Empty stdin", kind: "json")
            }
            guard let dict = try? JSONSerialization.jsonObject(with: inputData)
                    as? [String: Any]
            else {
                emitError("Stdin JSON is not an object", kind: "json")
            }
            if #available(macOS 26.0, *) {
                await runRecognizeDocuments(dict)
            } else {
                emitError(
                    "Document recognition requires macOS 26 or later.",
                    kind: "unavailable"
                )
            }
            return
        }

        // Warm the Vision document model. No stdin, no page, no failure mode
        // that matters — see runWarmDocuments.
        if args.contains("--warm-documents") {
            if #available(macOS 26.0, *) {
                await runWarmDocuments()
            } else {
                emitError(
                    "Document recognition requires macOS 26 or later.",
                    kind: "unavailable"
                )
            }
            return
        }

        // Probe mode — availability check only, no generation. Runs in tens
        // of milliseconds; safe to call from the wizard's onAppear.
        if args.contains("--probe") {
            let model = SystemLanguageModel.default
            switch model.availability {
            case .available:
                emitProbe(available: true, reason: nil)
            default:
                emitProbe(
                    available: false,
                    reason: "Apple Intelligence is not available on this device. " +
                            "Requires macOS 26+ on Apple Silicon with Apple Intelligence enabled."
                )
            }
        }

        // --supports-locale <code>: precheck whether the on-device model
        // accepts a given locale (#849). Returns {locale, supported}.
        // Cheaper than a full generation attempt that fails with
        // unsupportedLanguageOrLocale mid-flight. Daniel's case: route
        // to $large directly when document language is e.g. Korean
        // and Apple doesn't support it on this device.
        if let idx = args.firstIndex(of: "--supports-locale"), args.indices.contains(idx + 1) {
            let code = args[idx + 1]
            let model = SystemLanguageModel.default
            guard case .available = model.availability else {
                emitError(
                    "Apple Intelligence is not available on this device.",
                    kind: "unavailable"
                )
            }
            let supported = model.supportsLocale(Locale(identifier: code))
            let payload = LocaleSupportResponse(locale: code, supported: supported)
            if let data = try? JSONEncoder().encode(payload) {
                FileHandle.standardOutput.write(data)
            }
            exit(supported ? 0 : 0)  // Exit 0 either way; supported=false is a real answer, not an error
        }

        // NOTE: #848 (proactive --token-budget mode using
        // SystemLanguageModel.tokenUsage(for:) and .contextSize) requires
        // the macOS 26.4 SDK, which isn't on this machine's toolchain
        // yet (we're building against 26.2 SDK). Once Xcode/CLT update,
        // re-add the --token-budget mode. Until then we use a reactive
        // strategy on the Python side: catch the typed (decoding) error
        // from the bridge (which IS available — it's the existing
        // typed-error path from #843) and retry with smaller batches.

        // Availability check first — fail fast on machines without
        // Apple Intelligence (older OS, unsupported chip, not opted-in).
        let model = SystemLanguageModel.default
        guard case .available = model.availability else {
            emitError(
                "Apple Intelligence is not available on this device. " +
                "Requires macOS 26+ on Apple Silicon with Apple Intelligence enabled.",
                kind: "unavailable"
            )
        }

        // Read JSON request from stdin.
        let inputData = FileHandle.standardInput.readDataToEndOfFile()
        guard !inputData.isEmpty else {
            emitError("Empty stdin", kind: "json")
        }

        // Parse to [String: Any] first so we can dispatch on the presence
        // of a "schema" key without forcing a Codable schema for the
        // recursive schema tree.
        let raw: [String: Any]
        do {
            guard let dict = try JSONSerialization.jsonObject(with: inputData) as? [String: Any] else {
                emitError("Stdin JSON is not an object", kind: "json")
            }
            raw = dict
        } catch {
            emitError("Couldn't parse stdin as JSON: \(error)", kind: "json")
        }

        guard let prompt = raw["prompt"] as? String, !prompt.isEmpty else {
            emitError("Missing or empty 'prompt' field", kind: "json")
        }
        let instructions = raw["instructions"] as? String

        var options = GenerationOptions()
        if let temperature = raw["temperature"] as? Double {
            options.temperature = temperature
        }
        if let maxTokens = raw["max_tokens"] as? Int {
            options.maximumResponseTokens = maxTokens
        }

        // Optional guardrail mode (#850). "permissive" relaxes the on-
        // device safety filter for STRING-OUTPUT generations only —
        // useful for catalogue narratives over scholarly text with
        // literary profanity / court-record vocabulary that the
        // default guardrail false-positives. Apple's docs note this
        // has no effect on Generable / structured generation, where
        // the default guardrails always run. Caller should only pass
        // permissive on the free-form path.
        let guardrails: SystemLanguageModel.Guardrails
        if (raw["guardrails"] as? String) == "permissive" {
            guardrails = .permissiveContentTransformations
        } else {
            guardrails = .default
        }

        // Optional use-case selection (#853). Apple ships a specialised
        // model variant for content-tagging — one to a few lowercase
        // tags per input, semantically grouped (the model recognises
        // "hi", "hello", "yo" as one greet topic). Useful for the
        // keywords section of extract_all + per-section keywords_extract.
        // Falls back to the general-purpose model when not set.
        let chatModel: SystemLanguageModel
        if (raw["use_case"] as? String) == "content_tagging" {
            chatModel = SystemLanguageModel(
                useCase: .contentTagging, guardrails: guardrails
            )
        } else {
            chatModel = SystemLanguageModel(guardrails: guardrails)
        }

        let session: LanguageModelSession
        if let instructions, !instructions.isEmpty {
            session = LanguageModelSession(model: chatModel, instructions: instructions)
        } else {
            session = LanguageModelSession(model: chatModel)
        }

        // Structured-output dispatch — when "schema" is present, build a
        // GenerationSchema and use the grammar-constrained respond path
        // so the model physically cannot emit invalid JSON or truncate
        // mid-string. Result.content.jsonString gives us the canonical
        // JSON; Python parses it directly into a Pydantic instance.
        if let schemaDict = raw["schema"] as? [String: Any] {
            let dynamic: DynamicGenerationSchema
            do {
                try validateSchemaTree(schemaDict)
                dynamic = try buildDynamicSchema(schemaDict)
            } catch {
                emitError("Failed to build schema: \(error)", kind: "schema")
            }

            let schema: GenerationSchema
            do {
                schema = try GenerationSchema(root: dynamic, dependencies: [])
            } catch {
                emitError("GenerationSchema init failed: \(error)", kind: "schema")
            }

            // Default true (matches FoundationModels default). Python sets
            // false when our system instructions already describe the
            // schema, saving prompt tokens in Apple Intelligence's
            // ~4K context window (#843 follow-up).
            let includeSchemaInPrompt = (raw["include_schema_in_prompt"] as? Bool) ?? true

            do {
                let result = try await session.respond(
                    to: prompt,
                    schema: schema,
                    includeSchemaInPrompt: includeSchemaInPrompt,
                    options: options
                )
                let payload = StructuredSuccessResponse(
                    response_json: result.content.jsonString,
                    model: "apple-intelligence"
                )
                let data = try JSONEncoder().encode(payload)
                FileHandle.standardOutput.write(data)
            } catch {
                let (kind, message) = classifyGenerationError(error)
                emitError(message, kind: kind)
            }
            return
        }

        // Free-form path (existing behaviour) — no schema, returns a string.
        do {
            let result = try await session.respond(
                to: prompt,
                options: options
            )
            let payload = SuccessResponse(
                response: result.content,
                model: "apple-intelligence"
            )
            let data = try JSONEncoder().encode(payload)
            FileHandle.standardOutput.write(data)
        } catch {
            let (kind, message) = classifyGenerationError(error)
            emitError(message, kind: kind)
        }
    }
}
