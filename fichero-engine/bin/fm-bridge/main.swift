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
//   {"prompt": "...", "instructions": "...", "schema": <schema-tree>}
//
// Structured response (stdout):
//   {"response_json": "<raw json string from grammar-constrained output>",
//    "model": "apple-intelligence"}
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

@main
struct FmBridge {
    static func main() async {
        // Probe mode — availability check only, no generation. Runs in tens
        // of milliseconds; safe to call from the wizard's onAppear.
        if CommandLine.arguments.contains("--probe") {
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

        let session: LanguageModelSession
        if let instructions, !instructions.isEmpty {
            session = LanguageModelSession(instructions: instructions)
        } else {
            session = LanguageModelSession()
        }

        // Structured-output dispatch — when "schema" is present, build a
        // GenerationSchema and use the grammar-constrained respond path
        // so the model physically cannot emit invalid JSON or truncate
        // mid-string. Result.content.jsonString gives us the canonical
        // JSON; Python parses it directly into a Pydantic instance.
        if let schemaDict = raw["schema"] as? [String: Any] {
            let dynamic: DynamicGenerationSchema
            do {
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

            do {
                let result = try await session.respond(
                    to: prompt,
                    schema: schema,
                    includeSchemaInPrompt: true,
                    options: options
                )
                let payload = StructuredSuccessResponse(
                    response_json: result.content.jsonString,
                    model: "apple-intelligence"
                )
                let data = try JSONEncoder().encode(payload)
                FileHandle.standardOutput.write(data)
            } catch {
                emitError("Structured generation failed: \(error)", kind: "generation")
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
            emitError("Generation failed: \(error)", kind: "generation")
        }
    }
}
