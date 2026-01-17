# Workflow Model Sync Plan

## Status: COMPLETED

All phases have been implemented. The Swift types are now fully synchronized with Python Pydantic models.

## Goal
Ensure Pydantic models in Python are the single source of truth, with Swift using generated types or keeping manual types perfectly synchronized.

## Architecture
```
Python Pydantic Models → FastAPI → OpenAPI Spec → Swift OpenAPI Generator → Generated Types
                                                                              ↓
                                                     Manual WorkflowTypes.swift (NOW SYNCED)
```

## Complete Field Mapping (All ✅)

### WorkflowNode (Swift) vs NodeDef (Python)

| Python `NodeDef` | Swift `WorkflowNode` | Status |
|------------------|---------------------|--------|
| `id: str` | `id: String` | ✅ |
| `tool: str` | `tool: String` | ✅ |
| `input_ports: list[PortDef]` | `inputPorts: [PortInfo]` | ✅ |
| `output_ports: list[PortDef]` | `outputPorts: [PortInfo]` | ✅ |
| `input_mappings: list[InputMapping]` | `inputMappings: [InputMapping]` | ✅ |
| `inputs: dict[str, Any]` | `inputs: [String: AnyCodableValue]?` | ✅ ADDED |
| `config: dict[str, Any]` | `config: [String: AnyCodableValue]?` | ✅ |
| `output_schema: OutputSchema \| None` | `outputSchema: OutputSchema?` | ✅ ADDED |
| `position_x: float` | `positionX: Double` | ✅ |
| `position_y: float` | `positionY: Double` | ✅ |
| `label: str` | `label: String?` | ✅ |
| `description: str` | `description: String?` | ✅ |
| `enabled: bool` | `enabled: Bool` | ✅ |
| `provider_name: str` | `providerName: String?` | ✅ |
| `model_name: str` | `modelName: String?` | ✅ |
| `uses_llm: bool` | `usesLLM: Bool` | ✅ |

### WorkflowDefinition (Swift) vs WorkflowDef (Python)

| Python `WorkflowDef` | Swift `WorkflowDefinition` | Status |
|---------------------|---------------------------|--------|
| `id: str` | `id: String` | ✅ |
| `name: str` | `name: String` | ✅ |
| `description: str` | `description: String` | ✅ |
| `nodes: list[NodeDef]` | `nodes: [WorkflowNode]` | ✅ |
| `edges: list[EdgeDef]` | `edges: [WorkflowEdge]` | ✅ |
| `provider: str` | `provider: String` | ✅ |
| `model: str` | `model: String` | ✅ |
| `timeout_seconds: int` | `timeoutSeconds: Int` | ✅ ADDED |
| `max_retries: int` | `maxRetries: Int` | ✅ ADDED |
| `version: str` | `version: String` | ✅ ADDED |
| `created_at: str \| None` | `createdAt: String?` | ✅ ADDED |
| `updated_at: str \| None` | `updatedAt: String?` | ✅ ADDED |

### PortInfo (Swift) vs PortDef (Python)

| Python `PortDef` | Swift `PortInfo` | Status |
|-----------------|-----------------|--------|
| `id: str` | `id: String` | ✅ |
| `name: str` | `name: String` | ✅ |
| `port_type` | `portType: String` | ✅ |
| `data_type: DataType` | `dataType: String` | ✅ |
| `required: bool` | `required: Bool` | ✅ |
| `description: str` | `description: String` | ✅ |
| `default: Any` | `defaultValue: AnyCodableValue?` | ✅ ADDED |

### ToolInfo (Swift) vs ToolDef (Python)

| Python `ToolDef` | Swift `ToolInfo` | Status |
|-----------------|-----------------|--------|
| `name: str` | `name: String` | ✅ |
| `display_name: str` | `displayName: String` | ✅ |
| `description: str` | `description: String` | ✅ |
| `category: str` | `category: String` | ✅ |
| `icon: str` | `icon: String` | ✅ |
| `color: str` | `color: String` | ✅ |
| `input_ports` | `inputPorts: [PortInfo]` | ✅ |
| `output_ports` | `outputPorts: [PortInfo]` | ✅ |
| `config_schema` | `configSchema` | ✅ |
| `default_output_schema` | `defaultOutputSchema: [String: AnyCodableValue]?` | ✅ ADDED |
| `default_prompt` | `defaultPrompt: String?` | ✅ |
| `uses_llm` | `usesLLM: Bool` | ✅ |
| `supports_batch` | `supportsBatch: Bool` | ✅ |
| `supports_streaming` | `supportsStreaming: Bool` | ✅ |
| `supports_structured_output` | `supportsStructuredOutput: Bool` | ✅ |
| `sort_order` | `sortOrder: Int` | ✅ |

## Implementation Summary

### Phase 1: P0 Fields - COMPLETED
- Added `OutputSchema` struct to WorkflowTypes.swift
- Added `inputs` and `outputSchema` to `WorkflowNode`
- Updated `extractWorkflowNode()` to extract new fields
- Updated `createNodeDef()` to send new fields to backend

### Phase 2: P1 Fields - COMPLETED
- Added `defaultValue` to `PortInfo`
- Added `defaultOutputSchema` to `ToolInfo`
- Updated `convertToToolInfo()` to handle defaultOutputSchema
- Updated `convertPortResponseToPortInfo()` to handle default
- Updated `_port_to_response()` in Python to include default field

### Phase 3: P2 Fields - COMPLETED
- Added to `WorkflowDefinition`:
  - `timeoutSeconds: Int`
  - `maxRetries: Int`
  - `version: String`
  - `createdAt: String?`
  - `updatedAt: String?`
- Added custom decoder to handle missing fields gracefully

### Phase 4: Validation - COMPLETED
- Created `scripts/validate_model_sync.py` to detect model drift
- Created `scripts/start_backend.sh` for easy backend startup with validation
- Added `FICHERO_VALIDATE_MODELS=1` environment variable option in `main.py`
- Validation runs automatically on backend startup (logs warning if out of sync)

## Files Modified

### Swift
- `Fichero/Fichero/Models/WorkflowTypes.swift`
  - Added `OutputSchema` struct
  - Added `inputs`, `outputSchema` to `WorkflowNode`
  - Added `defaultValue` to `PortInfo`
  - Added `defaultOutputSchema` to `ToolInfo`
  - Added metadata fields to `WorkflowDefinition`

- `Fichero/Fichero/Services/WorkflowServiceGenerated.swift`
  - Updated `extractWorkflowNode()` with `extractInputs()`, `extractOutputSchema()`
  - Updated `createNodeDef()` to convert inputs and outputSchema
  - Updated `convertToToolInfo()` for defaultOutputSchema
  - Updated `convertPortResponseToPortInfo()` for default value
  - Updated `extractPorts()` and `createPortDef()` for default value

- `Fichero/Fichero/Services/ChatServiceGenerated.swift`
  - Fixed `listProviders()` to not send library path header (endpoint is app-wide)

### Python
- `src/fichero/api/routes/workflows.py`
  - Added `default: Any` field to `PortResponse`
  - Updated `_port_to_response()` to include default field

## Usage

### Starting the Backend
```bash
# Start with validation (recommended for development)
./scripts/start_backend.sh

# Start with OpenAPI regeneration + validation
./scripts/start_backend.sh --sync

# Start without validation (faster, for production)
./scripts/start_backend.sh --no-check

# Manual validation only
python3 scripts/validate_model_sync.py
```

### Environment Variables
- `FICHERO_VALIDATE_MODELS=1` - Enable model validation on FastAPI startup

## Next Steps
1. Consider adding validation to CI pipeline
2. Add pre-commit hook to run validation before commits
