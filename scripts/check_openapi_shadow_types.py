#!/usr/bin/env python3
"""OpenAPI shadow-type guardrail (§6b reform master plan — generated > manual).

Rule (prefer the generated contract type over a hand-written duplicate):

    > The Swift app must consume the generated `Components.Schemas.*` types from
    > FicheroAPIClient on the wire, not re-declare a manual `struct`/`enum` with
    > the SAME name as a backend OpenAPI schema. A hand-written type that shadows
    > a generated one drifts from the contract (missing/renamed fields), and the
    > round-trip silently loses data (see api_client.md).

This is static analysis over source text (it does NOT compile Swift). It loads
the schema names from the committed contract OpenAPI JSON and flags any
`struct`/`enum` in the app target (`fichero/fichero/`) whose name exactly equals
a `Components.Schemas.*` name. The generated client package itself is excluded.

The unit of violation is (file, TypeName) — keyed as `relpath::TypeName`, a
stable identity (never a line number). `KNOWN_VIOLATIONS` is the current backlog
of intentional/legacy display-model mirrors (e.g. `ResearchModels.swift` was
written to mirror `Components.Schemas.*` per #302). The guardrail PASSES today
and FAILS when a NEW manual type shadows a generated schema, and flags stale
entries when a shadow is removed.

NOTE: a shadow is not always wrong — some are display models that intentionally
mirror the contract. The point is that each one is a DELIBERATE choice recorded
here, so a new accidental duplicate is caught and reviewed.

Usage:
    scripts/check_openapi_shadow_types.py
    scripts/check_openapi_shadow_types.py --list
    scripts/check_openapi_shadow_types.py --help

Exit codes:
    0  every shadow is in KNOWN_VIOLATIONS
    1  a new shadow appeared, or a known entry is stale
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
CONTRACT_OPENAPI = ROOT / "fichero-engine" / "tests" / "contracts" / "openapi.json"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")
_TYPE_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|internal\s+|fileprivate\s+|final\s+|indirect\s+)*"
    r"(struct|enum)\s+(\w+)",
    re.MULTILINE,
)

# Current backlog of Swift types that shadow a Components.Schemas.* name.
# Keys are `relpath::TypeName`. Generated baseline (§6b).
KNOWN_VIOLATIONS: dict[str, str] = {
    "Models/Artifact.swift::Artifact": "§6b baseline — struct shadows Components.Schemas.Artifact",
    "Models/ComparisonTypes.swift::ComparisonHistoryResponse": "§6b baseline — struct shadows Components.Schemas.ComparisonHistoryResponse",
    "Models/Document.swift::DocType": "§6b baseline — enum shadows Components.Schemas.DocType",
    "Models/Document.swift::Document": "§6b baseline — struct shadows Components.Schemas.Document",
    "Models/Document.swift::FileType": "§6b baseline — enum shadows Components.Schemas.FileType",
    "Models/Document.swift::SearchResponse": "§6b baseline — struct shadows Components.Schemas.SearchResponse",
    "Models/Document.swift::SearchResult": "§6b baseline — struct shadows Components.Schemas.SearchResult",
    "Models/Document.swift::Status": "§6b baseline — enum shadows Components.Schemas.Status",
    "Models/AppleAvailabilityStore.swift::Status": "#2649 — local availability row-state model, distinct from the transport schema",
    "Models/Note.swift::Note": "§6b baseline — struct shadows Components.Schemas.Note",
    "Models/ResearchModels.swift::BrowserSaveRequest": "§6b baseline — struct shadows Components.Schemas.BrowserSaveRequest",
    "Models/ResearchModels.swift::BrowserSaveResponse": "§6b baseline — struct shadows Components.Schemas.BrowserSaveResponse",
    "Models/ResearchModels.swift::ChecklistItem": "§6b baseline — struct shadows Components.Schemas.ChecklistItem",
    "Models/ResearchModels.swift::ResearchChecklist": "§6b baseline — struct shadows Components.Schemas.ResearchChecklist",
    "Models/ResearchModels.swift::ResearchNote": "§6b baseline — struct shadows Components.Schemas.ResearchNote",
    "Models/ResearchModels.swift::ResearchPlan": "§6b baseline — struct shadows Components.Schemas.ResearchPlan",
    "Models/ResearchModels.swift::ResearchProject": "§6b baseline — struct shadows Components.Schemas.ResearchProject",
    "Models/ResearchModels.swift::ResearchStep": "§6b baseline — struct shadows Components.Schemas.ResearchStep",
    "Models/ResearchModels.swift::ResearchTask": "§6b baseline — struct shadows Components.Schemas.ResearchTask",
    "Models/SidebarChatTypes.swift::ChatMessage": "§6b baseline — struct shadows Components.Schemas.ChatMessage",
    "Models/SidebarChatTypes.swift::DocumentSource": "§6b baseline — struct shadows Components.Schemas.DocumentSource",
    "Models/WorkflowChain.swift::ChainExecutionStatusResponse": "§6b baseline — struct shadows Components.Schemas.ChainExecutionStatusResponse",
    "Models/WorkflowChain.swift::ChainListResponse": "§6b baseline — struct shadows Components.Schemas.ChainListResponse",
    "Models/WorkflowChain.swift::CreateChainRequest": "§6b baseline — struct shadows Components.Schemas.CreateChainRequest",
    "Models/WorkflowChain.swift::ExecuteChainRequest": "§6b baseline — struct shadows Components.Schemas.ExecuteChainRequest",
    "Models/WorkflowResponseTypes.swift::NodeResponse": "§6b baseline — struct shadows Components.Schemas.NodeResponse",
    "Models/WorkflowResponseTypes.swift::WorkflowResponse": "§6b baseline — struct shadows Components.Schemas.WorkflowResponse",
    "Models/WorkflowSupportTypes.swift::InputMapping": "§6b baseline — struct shadows Components.Schemas.InputMapping",
    "Models/WorkflowSupportTypes.swift::OutputSchema": "§6b baseline — struct shadows Components.Schemas.OutputSchema",
    "Services/ActionsService.swift::CreateActionRequest": "§6b baseline — struct shadows Components.Schemas.CreateActionRequest",
    "Services/AnnotationService.swift::AnnotationKind": "§6b baseline — enum shadows Components.Schemas.AnnotationKind",
    "Services/AnnotationService.swift::AnnotationListResponse": "§6b baseline — struct shadows Components.Schemas.AnnotationListResponse",
    "Services/AutomationServiceTypes.swift::CreateScheduleRequest": "§6b baseline — struct shadows Components.Schemas.CreateScheduleRequest",
    "Services/AutomationServiceTypes.swift::CreateTriggerRequest": "§6b baseline — struct shadows Components.Schemas.CreateTriggerRequest",
    "Services/AutomationServiceTypes.swift::ScheduleConfigRequest": "§6b baseline — struct shadows Components.Schemas.ScheduleConfigRequest",
    "Services/AutomationServiceTypes.swift::TriggerConfigRequest": "§6b baseline — struct shadows Components.Schemas.TriggerConfigRequest",
    "Services/BatchTypes.swift::CreateBatchRequest": "§6b baseline — struct shadows Components.Schemas.CreateBatchRequest",
    "Services/ChatServiceTypes.swift::ConversationSummary": "§6b baseline — struct shadows Components.Schemas.ConversationSummary",
    "Services/ChatServiceTypes.swift::ExtractTextResponse": "§6b baseline — struct shadows Components.Schemas.ExtractTextResponse",
    "Services/CheckpointTypes.swift::CheckpointHistoryResponse": "§6b baseline — struct shadows Components.Schemas.CheckpointHistoryResponse",
    "Services/CheckpointTypes.swift::CheckpointSnapshot": "§6b baseline — struct shadows Components.Schemas.CheckpointSnapshot",
    "Services/ImportServiceTypes.swift::IngestFileRequest": "§6b baseline — struct shadows Components.Schemas.IngestFileRequest",
    "Services/ImportServiceTypes.swift::IngestFolderRequest": "§6b baseline — struct shadows Components.Schemas.IngestFolderRequest",
    "Services/ImportService.swift::IngestTaskStatus": "§6b baseline — struct shadows Components.Schemas.IngestTaskStatus",
    "Services/IntegrationsServiceTypes.swift::IntegrationItem": "§6b baseline — struct shadows Components.Schemas.IntegrationItem",
    "Services/MCPService.swift::CreateMCPServerRequest": "§6b baseline — struct shadows Components.Schemas.CreateMCPServerRequest",
    "Services/MCPService.swift::MCPServerResponse": "§6b baseline — struct shadows Components.Schemas.MCPServerResponse",
    "Services/MCPService.swift::MCPToolInfo": "§6b baseline — struct shadows Components.Schemas.MCPToolInfo",
    "Services/MCPService.swift::UpdateMCPServerRequest": "§6b baseline — struct shadows Components.Schemas.UpdateMCPServerRequest",
    "Services/ModelComparisonTypes.swift::CompareRequest": "§6b baseline — struct shadows Components.Schemas.CompareRequest",
    "Services/ModelComparisonTypes.swift::ModelSpec": "§6b baseline — struct shadows Components.Schemas.ModelSpec",
    "Services/ModelComparisonTypes.swift::NodeCompareRequest": "§6b baseline — struct shadows Components.Schemas.NodeCompareRequest",
    "Services/ModelComparisonTypes.swift::ToolCompareRequest": "§6b baseline — struct shadows Components.Schemas.ToolCompareRequest",
    "Services/ModelComparisonTypes.swift::VisionCompareRequest": "§6b baseline — struct shadows Components.Schemas.VisionCompareRequest",
    "Services/ModelServiceTypes.swift::HFModelInfo": "§6b baseline — struct shadows Components.Schemas.HFModelInfo",
    "Services/ModelServiceTypes.swift::HFTaskCategory": "§6b baseline — struct shadows Components.Schemas.HFTaskCategory",
    "Services/NoteService.swift::NoteListResponse": "§6b baseline — struct shadows Components.Schemas.NoteListResponse",
    "Services/ProviderServiceTypes.swift::ConnectionTestResponse": "§6b baseline — struct shadows Components.Schemas.ConnectionTestResponse",
    "Services/ProviderServiceTypes.swift::ModelInfo": "§6b baseline — struct shadows Components.Schemas.ModelInfo",
    "Services/ProviderServiceTypes.swift::ProviderResponse": "§6b baseline — struct shadows Components.Schemas.ProviderResponse",
    "Services/ProviderServiceTypes.swift::StatusResponse": "§6b baseline — struct shadows Components.Schemas.StatusResponse",
    "Services/ProviderServiceTypes.swift::UserModelResponse": "§6b baseline — struct shadows Components.Schemas.UserModelResponse",
    "Services/SearchService.swift::EmbeddingStatsResponse": "§6b baseline — struct shadows Components.Schemas.EmbeddingStatsResponse",
    "Services/SpatialLibraryProjector.swift::Document": "#2712 — local projector display model; consume generated Components.Schemas.Document when Spatial folds into the library",
    "Services/WorkflowRunResponse.swift::WorkflowRunResponse": "§6b baseline — struct shadows Components.Schemas.WorkflowRunResponse",
    "Services/WorkflowStreamTypes.swift::ExecuteAcceptedResponse": "§6b baseline — struct shadows Components.Schemas.ExecuteAcceptedResponse",
    "Views/Library/Workspace/WorkspaceItemPicker.swift::WorkspaceCuratedItem": "#2649 — local curated-item projection for picker state, distinct from the wire payload",
    "Views/Settings/AIDefaults.swift::AIDefaults": "§6b baseline — struct shadows Components.Schemas.AIDefaults",
    "Views/Workflow/WorkflowOutputLog+Models.swift::StepStatus": "§6b baseline — enum shadows Components.Schemas.StepStatus",
}


def schema_names(contract: Path = CONTRACT_OPENAPI) -> set[str]:
    data = json.loads(contract.read_text())
    return set(data.get("components", {}).get("schemas", {}).keys())


def _strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _LINE_COMMENT.sub("", text)


def scan(swift_dir: Path = SWIFT_DIR, contract: Path = CONTRACT_OPENAPI) -> dict[str, str]:
    names = schema_names(contract)
    found: dict[str, str] = {}
    for path in sorted(swift_dir.rglob("*.swift")):
        if "Tests" in path.parts:
            continue
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        cleaned = _strip_comments(source)
        rel = path.relative_to(swift_dir).as_posix()
        for m in _TYPE_RE.finditer(cleaned):
            kind, name = m.group(1), m.group(2)
            if name in names:
                found[f"{rel}::{name}"] = f"{kind} shadows Components.Schemas.{name}"
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"OpenAPI shadow types ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"OpenAPI shadow-type guardrail: scanned {SWIFT_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} manual type(s) shadow a Components.Schemas.* name; {len(known)} known.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new manual type(s) shadowing a generated schema:")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: consume the generated `Components.Schemas.*` type instead of "
            "re-declaring it. If a distinct display model is genuinely required, "
            f"add it to KNOWN_VIOLATIONS with a reason. Rule: {RULE_DOC} §6b."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
        return 1

    print("\n✓ No new manual types shadowing generated schemas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
