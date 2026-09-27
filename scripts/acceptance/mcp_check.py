"""Step 2b: the same reads through the MCP server's own tool functions.

Calls the tool functions in `fichero_mcp.server` in-process (each is one FicheroClient call,
exactly what the stdio server runs per request) and lists every tool registered, so the
report can say which levels an agent can reach and which it cannot.

Writes ACCEPTANCE_OUT/mcp.json. Starts and stops its own engine.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import client_env, engine, load, save  # noqa: E402


def _fn(tool):
    fn = getattr(tool, "fn", tool)

    def call(*a, **k):
        r = fn(*a, **k)  # tools return the client's typed models; MCP serialises them to JSON
        return r.model_dump(mode="json") if hasattr(r, "model_dump") else r

    return call


def main() -> None:
    rows = load("import.json")
    pages = {(r["key"], Path(p["name"]).stem): p for r in rows for p in r["pages"] if p.get("image")}
    syriac = pages[("syriac-rtl", "0002_00000017")]
    clm = pages[("clm13027-mufi", "38r")]
    out: dict = {}
    with engine():
        client_env()
        from fichero_mcp import server  # noqa: PLC0415 -- after the env points at our engine

        tools = asyncio.run(server.mcp.list_tools()) if hasattr(server.mcp, "list_tools") else []
        names = sorted(t.name for t in tools)
        out["tool_count"] = len(names)
        out["segment_like_tools"] = [n for n in names if any(k in n for k in ("segment", "page", "reading", "text", "order", "pass"))]
        for label, page in (("syriac", syriac), ("clm", clm)):
            segs = _fn(server.fichero_segments)(page["id"])
            kinds: dict[str, int] = {}
            for s in segs["segments"]:
                kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
            first_word_or_line = next(s for s in segs["segments"] if s["kind"] in ("word", "line") and s["kind"] != "region")
            one = _fn(server.fichero_segment)(first_word_or_line["id"])
            exp = _fn(server.fichero_page_export)(page["id"], "pagexml" if label == "syriac" else "alto")
            out[label] = {
                "kinds": kinds,
                "segment_text_field": first_word_or_line.get("text"),
                "one_segment_text_field": (one.get("segment") or {}).get("text"),
                "one_segment_has_parent": "parent_segment_id" in (one.get("segment") or {}),
                "export_bytes": len(exp.get("content") or ""),
                "export_losses": exp.get("losses"),
            }
    save("mcp.json", out)
    print(out)


if __name__ == "__main__":
    main()
