"""`builder spec`: the brief for the spec-writer role (dev-workflows.tool.spec). It writes the brief and starts nothing;
`builder run` starts the worker. The guards are named in words so the writer meets them before they run."""
from __future__ import annotations

from pathlib import Path

from fichero_builder import brief_tool

SPECS = "docs/contributor_manual/specs"
SHAPE = """## Build order
### Stage N — title                      (optional)
#### Step N.M — title (#NNNN)            (issue number optional until filed)
- Behaviours: `id.one`, `id.two`
- Tests: path/a.py, path/b.py
- Depends on: N.M, ...                   (optional; default: the step before, in-stage)
- Size: S | M | L"""
GUARDS = f"""The spec guards (scripts/) run on your file; write it so they pass:
- check_spec_behaviors_are_tagged: every behaviour bullet is `- `<area>.<id>` [TAG] — what is observed` with a tag OK, BROKEN, GAP, PARTIAL, MISSING or PROPOSED.
- check_spec_build_order_shape: the build order has exactly this shape; every behaviour tagged MISSING, GAP, BROKEN or PARTIAL is in exactly one step; every step has Behaviours and Tests; no step is Size L or lists more than five behaviours; Depends on points only at earlier steps.
{SHAPE}
- check_specs_have_tests: an APPROVED spec carries a filled test matrix and is cited by at least one test (the owner approves; you do not).
- check_spec_milestones and check_spec_manual_refs: a `> Milestone: <name>` line and a `> Manual: <path or TBD — what it must say>` line in the header."""


def template(root) -> str:
    for name in ("TEMPLATE.md", "_TEMPLATE.md"):
        f = Path(root) / SPECS / name
        if f.is_file():
            return f"(from {SPECS}/{name})\n\n{f.read_text()}"
    return f"(no template file; the headings the build-order guard expects)\n\n{SHAPE}"


def brief(issue: dict, root) -> str:
    return "\n".join([
        "You are the spec-writer in the dev harness. Write ONE spec file under "
        f"{SPECS}/<area>/ (pick the area folder that fits the issue) for the issue below.",
        "The file's header carries `> **Status: PROPOSED**`. Never write APPROVED: the owner approves by editing that line, "
        "and nothing in the spec is built before that. Do not write code or tests; do not touch any other file.",
        "Commit it on this branch (message ends `Part of #" + str(issue["number"]) + "`), then print on its own line: DONE <short sha>.",
        "", GUARDS, "", "## The spec template", template(root), "", "## The issue", brief_tool.build(issue, repo=str(root))])


def run(issue_number: int, out, root, *, gh: str = "gh") -> str:
    text = brief(brief_tool.fetch_issue(issue_number, gh=gh), root)
    Path(out).write_text(text)
    return text
