#!/usr/bin/env python3
"""Classify closed issues from version milestones → feature milestones by title heuristic."""
import json
import subprocess
import sys
import re

# Feature milestone name → GitHub milestone number
FEATURE_MILESTONES = {
    "KG Single-Path": 55,
    "Workflows": 54,
    "Search": 17,
    "Chat": 22,
    "Importers": 57,
    "Exporter": 14,
    "Translation": 58,
    "Image Editing": 13,
    "MCP": 52,
    "Mind Palace": 12,
    "Researcher": 53,
    "NER": 59,
    "Hermeneutics": 37,
    "Activity & Automation": 56,
    "Infrastructure": 11,
    "Settings & Providers": 20,
    "Onboarding": 60,
    "Epistemic Platform Expansion": 6,
}

# Version milestones (id → name)
VERSION_MILESTONES = {
    9: "0.0.1 - Core Library",
    8: "0.0.2 - Backend Merge + Bug Fixes",
    50: "0.0.3",
}

# Ordered classification rules: (feature_milestone_name, [keywords])
# First match wins; keywords checked against lowercased title
RULES = [
    # Highly specific domains first
    ("Translation", ["translation", "translate", "deepl", "language identif"]),
    ("Hermeneutics", ["hermeneutic", "interpretation framework", "controlled predicate", "controlled vocab"]),
    ("Mind Palace", ["mind palace", "spatial library", "realitykit", "vision pro", "spatial knowledge", "spatial scene", "room list"]),
    ("MCP", ["mcp server", "mcp tool", " mcp ", "fastmcp", "mcp:"]),
    ("Researcher", ["researcher agent", "research agent", "autonomous research", "research workspace", "research browser", "multilingual archival", "archival research"]),
    ("NER", ["spacy", "spaCy", "ner model", "plagiarism", "sentiment analysis", "named entity recog"]),
    ("Image Editing", ["image edit", "crop", "rotate", "remove background", "image segment", "edit chain", "non-destructive", "image magnif", "loupe", "image viewer", "magnifier"]),
    ("Exporter", ["export", "word export", "excel export", "markdown export", "netlify", "static html", "static site", "dmg", "sparkle", "notarize", "app store", "release build", "bundle", "codesign"]),
    ("Chat", ["rag chat", "chat-with-sources", "model comparison", "model-comparison", "chat interface", "conversation", " chat "]),
    ("Search", ["search result", "search bar", "search ux", "search column", "search v", "semantic search", "hybrid retriev", "hybrid bm25", "bm25", "relevance threshold", "search returns", "search filter", "search: "]),
    ("KG Single-Path", [
        "kg ", " kg:", "knowledge graph", "knowledge claim", "entity type", "entity profile", "entity browser",
        "entity extract", "entity dedup", "entity digest", "extract all entit", "kg viz", "kg visual",
        "kg claims", "kg entities", "kg navigation", "kg temporal", "kg spatial", "kg quality",
        "kg focus", "claim inspector", "claim card", "ontology", "kg/", "svo", "triple",
        "kg extractor", "epistemology", "epistemic graph", "kg prediction", "contradiction",
        "claim text", "claim link", "claim crud", "claim extract", "entity writer",
        "entity_ids", "knowledge surface", "kg empty", "kg payload",
        "claims list", "claim focus", "claim summary", "entity focus",
        "extract_all", "catalogue", "catalogu",  # catalogue is KG workflow
        "extractor", "claim writer", "entity upsert", "claim upsert",
        "kg zero", "kg row", "entity count", "claim count",
        "annotation", "predicate", "svo_verb", "slug_verb",
    ]),
    ("Workflows", [
        "workflow", "tool node", "node editor", "node config", "workflow canvas",
        "workflow chain", "workflow editor", "workflow library", "workflow template",
        "workflow preset", "workflow execution", "workflow run", "run workflow",
        "workflow json", "workflow import", "workflow export", "workflow tool",
        "langgraph", "workflow builder", "workflow registry", "workflow executor",
        "workflow definition", "workflow graph", "workflow param",
        "node palette", "tool palette", "workflow files node", "files node",
        "workflow node", "batch process", "batch workflow",
        "transcribe node", "clean text", "clean_text",
        "prompt preview", "workflow qa", "prompt node",
    ]),
    ("Activity & Automation", [
        "activity", "automation", "schedule", "trigger", "execution monitor",
        "run title", "execution view", "execution history", "workflow execution view",
        "execution log", "activity monitor", "activity viewer", "real-time progress",
        "execution progress", "activity run",
    ]),
    ("Importers", [
        "import", "ingest", "drag-in", "drag and drop", "drop zone",
        "file picker", "folder watch", "folder ingest", "cloud import",
        "xlsx", "sidecar", "bookmark", "security-scoped",
        "drop destination", "import mode", "copy mode", "link mode",
        "drag import", "file import", "ingest mode", "ingest pipeline",
    ]),
    ("Settings & Providers", [
        "provider", "api key", "llm provider", "local model", "settings default",
        "settings ui", "model catalog", "model select", "model tier",
        "model management", "model config", "settings:", "settings →",
        "provider mgmt", "provider setting", "provider api", "llm config",
        "defaults:", "settings page", "ollama", "lm studio", "omlx",
        "mlx ", "apple intelligence", "local model", "model discovery",
    ]),
    ("Infrastructure", [
        "auth", "rate limit", "observability", "migration", "test fixture",
        "contract test", "openapi", "database", "devonthink", "bookends integration",
        "tinderbox integration", "performance", "memory", "crash", "api contract",
        "health", "middleware", "duckdb", "lancedb", "db.", "db_",
        "ruff", "pytest", "swiftlint", "xcode build", "swift build",
        "pbxproj", "xcodeproj", "build phase", "build error",
        "test:", "tests:", "unit test", "integration test",
        "ci ", "endpoint", "route ", "router", "api/", "fastapi",
        "pydantic", "schema", "backend ", "engine ", "server ",
        "port ", "launch", "startup", "boot", "restart", "uvicorn",
        "backend connection", "backend startup", "engine startup",
        "log stream", "logging", "error state", "error service",
        "error handling", "exception", "403", "404", "500",
        "response model", "response validation",
        "verify gate", "gate task", "verification",
        "ssh", "remote", "acenet",
    ]),
    ("Onboarding", [
        "onboard", "toolbar", "reading surface", "first-run", "welcome",
        "sidebar", "pane width", "split view", "navigation bar", "nav bar",
        "sidebar nav", "sidebar mode", "layout", "ux:", "ux ",
        "view mode", "inspector", "inspector panel", "inspector tab",
        "pane layout", "pane focus", "pane min-width", "window",
        "keyboard nav", "keyboard shortcut", "menu item", "menu command",
        "sidebar item", "sidebar column", "sidebar select",
        "document list", "library view", "grid view", "table view",
        "list view", "thumbnail", "icon list", "grid icon",
        "document viewer", "content view", "reading view",
        "tab title", "center image", "scroll", "zoom",
        "font", "margin", "background", "color", "style",
        "ui:", "ux:", "feat: phase", "phase g",
    ]),
    # Final fallback
    ("Infrastructure", []),  # catch-all
]


def classify(title: str) -> str:
    t = title.lower()
    for feature, keywords in RULES:
        if not keywords:  # catch-all
            return feature
        for kw in keywords:
            if kw.lower() in t:
                return feature
    return "Infrastructure"


def fetch_issues(milestone_id: int) -> list[dict]:
    issues = []
    page = 1
    while True:
        result = subprocess.run(
            ["gh", "api", f"repos/dtubb/fichero/issues?milestone={milestone_id}&state=closed&per_page=100&page={page}",
             "-q", ".[] | {number: .number, title: .title}"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            break
        lines = result.stdout.strip().split('\n')
        if not lines or lines == ['']:
            break
        batch = []
        for line in lines:
            if line.strip():
                try:
                    batch.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return issues


def main():
    dry_run = "--dry-run" in sys.argv

    all_updates = []  # (issue_number, old_ms, feature_ms_name, feature_ms_id)
    counts = {}

    for ms_id, ms_name in VERSION_MILESTONES.items():
        print(f"\nFetching closed issues from milestone: {ms_name} (id={ms_id})")
        issues = fetch_issues(ms_id)
        print(f"  Found {len(issues)} issues")

        for issue in issues:
            num = issue["number"]
            title = issue["title"]
            feature = classify(title)
            feature_id = FEATURE_MILESTONES[feature]
            all_updates.append((num, ms_name, feature, feature_id, title))
            counts[feature] = counts.get(feature, 0) + 1

    print(f"\nClassification summary:")
    for feat, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {feat}: {cnt}")
    print(f"  TOTAL: {sum(counts.values())}")

    if dry_run:
        print("\nDry run — sample assignments:")
        for num, ms, feat, fid, title in all_updates[:30]:
            print(f"  #{num} → {feat}: {title[:80]}")
        return

    print(f"\nApplying {len(all_updates)} milestone updates...")
    log_lines = []
    errors = []

    for i, (num, ms, feat, fid, title) in enumerate(all_updates):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(all_updates)}")
        result = subprocess.run(
            ["gh", "issue", "edit", str(num), "--milestone", feat],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            errors.append(f"#{num}: {result.stderr.strip()}")
            log_lines.append(f"ERROR #{num} → {feat}: {result.stderr.strip()}")
        else:
            log_lines.append(f"#{num} → {feat} (was: {ms}): {title[:60]}")

    # Write log
    log_path = "agent-work/proposals/2026-05-30-closed-issue-refile-log.txt"
    with open(log_path, "w") as f:
        f.write(f"Closed-issue re-filing log — {len(all_updates)} issues\n")
        f.write("=" * 60 + "\n\n")
        f.write("Classification summary:\n")
        for feat, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            f.write(f"  {feat}: {cnt}\n")
        f.write("\nDetailed log:\n")
        for line in log_lines:
            f.write(line + "\n")

    print(f"\nDone. {len(errors)} errors.")
    if errors:
        print("Errors:", errors[:10])
    print(f"Log written to {log_path}")


if __name__ == "__main__":
    main()
