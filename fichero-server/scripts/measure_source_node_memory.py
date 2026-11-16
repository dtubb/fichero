#!/usr/bin/env python3
"""Peak memory of the workflow source node over a folder of N pages (`workflows.source-node-memory-measured`, Step 2.5, #4390).

Builds a TEMPORARY library (a throwaway directory, deleted at the end; never the app's database) holding one folder of N page
documents, each with `page_content` of --text-kb KB, then runs the `folder` source tool over it exactly as a workflow's first node
does and prints one JSON line: peak RSS before and after, the growth, and the size of what the node handed on in state.

    python fichero-server/scripts/measure_source_node_memory.py --pages 50                # proves it works
    python fichero-server/scripts/measure_source_node_memory.py --pages 500 --text-kb 40  # the 500-page baseline (run on the M4 iMac)

Run each size in its own process: peak RSS only ever grows within one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _rss_peak_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # macOS reports bytes, Linux KB


def _text(kb: int, seed: int) -> str:
    line = f"page {seed} the quick brown fox jumps over the lazy dog and writes a long line of reading text. "
    return (line * (kb * 1024 // len(line) + 1))[: kb * 1024]


async def _run(pages: int, text_kb: int) -> dict:
    from fichero_server.db import Database
    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.tools.sources import folder_tool

    os.environ["FICHERO_SOURCE_MAX_FILES"] = "0"  # the cap is not what is being measured
    with tempfile.TemporaryDirectory(prefix="fichero-source-memory-") as tmp:
        library = str(Path(tmp) / "measure.fichero")
        db = Database(Path(tmp) / "measure.duckdb")
        folder = Document(id="measure-folder", name="Measured folder", doc_type=DocType.folder)
        db.save(folder)
        for i in range(pages):
            db.save(Document(id=f"page{i:06d}", name=f"page_{i:06d}.jpg", doc_type=DocType.file, file_type=FileType.image,
                             path=f"files/pa/page_{i:06d}.jpg", parent_id=folder.id, page_content=_text(text_kb, i)))
        before = _rss_peak_bytes()
        with patch("fichero_server.workflows.tools.sources.db_manager") as manager, \
             patch("fichero_server.workflows.tools.sources._resolve_abs_path", side_effect=lambda doc, lib: f"{lib}/{doc.path}"):
            manager.get_database.return_value = db
            result = await folder_tool({"folder_id": folder.id}, {"library_path": library},
                                       LLMConfig(provider="openai", model="gpt-4o", api_key="x"))
        after = _rss_peak_bytes()
        held = sum(len(d.get("page_content") or "") for d in result["documents"])
        return {
            "pages": pages, "text_kb_each": text_kb, "documents_returned": len(result["documents"]),
            "page_content_bytes_held_in_state": held, "json_bytes_of_state_documents": len(json.dumps(result["documents"])),
            "peak_rss_before_bytes": before, "peak_rss_after_bytes": after, "peak_rss_growth_bytes": after - before,
            "platform": sys.platform,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, default=50)
    parser.add_argument("--text-kb", type=int, default=40, help="page_content size of each page, KB (default 40, a dense printed page)")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.pages, args.text_kb))))


if __name__ == "__main__":
    main()
