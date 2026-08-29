#!/usr/bin/env python3
"""Exercise tools against a REAL model and show what they actually did.

The unit suite mocks the model, so it proves a tool's plumbing and nothing
about its answer. That is how Extract Table shipped returning the page's
transcription verbatim for weeks: every passthrough test used Transcribe's
tool config, so nothing ever asked "did the model get called at all?"

This runs the real thing and writes down, per tool: the input it was given,
the PROMPT that actually went over the wire, the model's raw output, the
tokens and the wall clock. Then you read the report and judge.

    # everything that can take a page image, on one document
    scripts/exercise_tools.py --library ~/Fichero/Marshall.fichero \
        --document a55046a1 --model openrouter:google/gemini-3.1-flash-lite

    # one tool, from the page's edited text instead of its image
    scripts/exercise_tools.py --library ... --document ... \
        --tools text_translate --input content

`--input` is the question this script exists to make answerable: the same
tool run on the page image, on the page's (possibly hand-corrected) content,
or on both, is three different answers. Nothing writes to the library —
`save_to_db` is off for every call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fichero-server" / "src"))


# --------------------------------------------------------------------------
# Prompt recorder
# --------------------------------------------------------------------------


class Recorder:
    """Wraps llm.vision / llm.chat so the prompt that goes over the wire is
    captured with the call, not reconstructed from the tool's config afterwards
    (which is how you end up documenting a prompt nobody sent)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._orig: dict[str, Any] = {}

    def install(self) -> None:
        from fichero_server import llm

        for name in ("vision", "chat"):
            self._orig[name] = getattr(llm, name)

        async def vision(images, prompt, config, **kw):
            return await self._record("vision", prompt, config, images, kw)

        async def chat(messages, config, **kw):
            prompt = messages
            if isinstance(messages, list):
                prompt = "\n\n".join(
                    str(m.get("content") if isinstance(m, dict) else m)
                    for m in messages
                )
            return await self._record("chat", prompt, config, None, kw, messages)

        llm.vision = vision
        llm.chat = chat

    def restore(self) -> None:
        from fichero_server import llm

        for name, fn in self._orig.items():
            setattr(llm, name, fn)

    async def _record(self, kind, prompt, config, images, kw, first_arg=None):
        started = time.monotonic()
        entry: dict[str, Any] = {
            "kind": kind,
            "provider": getattr(config, "provider", None),
            "model": getattr(config, "model", None),
            "max_tokens": getattr(config, "max_tokens", None),
            "temperature": getattr(config, "temperature", None),
            "prompt": prompt if isinstance(prompt, str) else repr(prompt),
            "image_count": len(images) if images else 0,
        }
        try:
            if kind == "vision":
                out = await self._orig["vision"](images, prompt, config, **kw)
            else:
                out = await self._orig["chat"](first_arg, config, **kw)
            entry["output"] = out if isinstance(out, str) else repr(out)
            return out
        except Exception as exc:  # noqa: BLE001 — the report wants the failure
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            entry["seconds"] = round(time.monotonic() - started, 2)
            self.calls.append(entry)


# --------------------------------------------------------------------------
# What each tool can be fed
# --------------------------------------------------------------------------


def _port_ids(tool_def, side: str) -> set[str]:
    ports = getattr(tool_def, f"{side}_ports", None) or []
    return {getattr(p, "id", "") for p in ports}


# Categories that want a media file this script is not handing them. Feeding a
# JPEG to audio_transcribe buys a whisper stack trace and nothing else, and a
# report full of those hides the failures that matter.
_MEDIA_ONLY_CATEGORIES = {"audio", "video"}
_MEDIA_ONLY_TOOLS = {"audio_transcribe", "video_describe", "segment", "compare"}


def tool_prompt(tool_def, config: dict | None = None) -> str:
    """The prompt this tool would send for a given config.

    `prompt_builder` is the live one — it reads output_style, language, target
    format — and `default_prompt` is the frozen fallback the editor shows. Ask
    for the builder first or the report documents a prompt nobody sends.
    """
    builder = getattr(tool_def, "prompt_builder", None)
    if callable(builder):
        try:
            return builder(config or {})
        except Exception as exc:  # noqa: BLE001 — a bad builder is a finding
            return f"<prompt_builder raised {type(exc).__name__}: {exc}>"
    return getattr(tool_def, "default_prompt", None) or "<no prompt registered>"


def build_inputs(tool_def, *, mode: str, file_path: str, document: dict) -> dict | None:
    """Map --input onto the tool's actual ports, or None if it can't be fed.

    A tool that takes `files` is asking for the page as an IMAGE. A tool that
    takes `text` is asking for the page as CONTENT — which for a reviewed
    document is the hand-corrected transcription, not the original OCR.
    """
    if (getattr(tool_def, "category", "") in _MEDIA_ONLY_CATEGORIES
            or tool_def.name in _MEDIA_ONLY_TOOLS):
        return None

    ins = _port_ids(tool_def, "input")
    content = (document.get("page_content") or "").strip()
    payload: dict[str, Any] = {"save_to_db": False}

    wants_image = "files" in ins
    wants_text = "text" in ins

    if mode in ("page", "both") and wants_image:
        payload["files"] = [file_path]
        payload["documents"] = [document]
    if mode in ("content", "both") and wants_text:
        if not content:
            return None
        payload["text"] = content
        payload.setdefault("documents", [document])

    if "files" not in payload and "text" not in payload:
        return None
    return payload


# --------------------------------------------------------------------------


async def run_one(name, tool_def, inputs, state, llm_config, recorder,
                  document_content: str = ""):
    from fichero_server.workflows.registry import get_tool

    fn = get_tool(name)
    before = len(recorder.calls)
    started = time.monotonic()
    row: dict[str, Any] = {
        "tool": name,
        "display_name": getattr(tool_def, "display_name", name),
        "inputs": {
            k: (v if k not in ("documents",) else f"<{len(v)} document(s)>")
            for k, v in inputs.items()
            if k != "text"
        },
        "input_text_chars": len(inputs.get("text", "")),
    }
    out: Any = None
    try:
        out = await fn(inputs, state, llm_config)
        text = out.get("text") if isinstance(out, dict) else None
        row["ok"] = not (isinstance(out, dict) and out.get("error"))
        row["error"] = (out or {}).get("error") if isinstance(out, dict) else None
        row["output"] = text if isinstance(text, str) else json.dumps(
            out, default=str
        )[:4000]
        row["value_is_structured"] = isinstance(
            (out or {}).get("value") if isinstance(out, dict) else None, (dict, list)
        )
    except Exception as exc:  # noqa: BLE001 — one bad tool must not end the run
        row["ok"] = False
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["output"] = ""
    row["seconds"] = round(time.monotonic() - started, 2)
    row["registered_prompt"] = tool_prompt(tool_def, inputs)
    row["model_calls"] = recorder.calls[before:]
    # The single most useful line in the report: a tool that produced an answer
    # WITHOUT calling a model either short-circuited on cached/extracted text or
    # never did its job. Both are worth seeing at a glance.
    row["called_model"] = len(row["model_calls"]) > 0
    # "No model call" has two innocent explanations and one guilty one, and the
    # report is worthless if it cannot tell them apart: the tool reused a cached
    # artifact (skip_if_artifact_exists), or it took the pre-extracted-text
    # passthrough — versus it silently did nothing. Name the reason.
    reused = (out or {}).get("reused_count") if isinstance(out, dict) else 0
    row["reused_count"] = reused or 0
    if row["called_model"]:
        row["why_no_call"] = None
    elif row["reused_count"]:
        row["why_no_call"] = f"reused {row['reused_count']} cached artifact(s)"
    elif inputs.get("text"):
        row["why_no_call"] = "answered from the text it was handed"
    elif (row["output"] or "").strip() == (document_content or "").strip() and (
        document_content or ""
    ).strip():
        # The signal that caught Extract Table echoing the transcription. For
        # Transcribe this is the correct pre-extracted-text passthrough; for
        # anything else it means the tool never did its job.
        row["why_no_call"] = (
            "returned the page's content VERBATIM — correct only for Transcribe"
        )
    elif row["ok"]:
        row["why_no_call"] = "UNEXPLAINED — the tool answered without a model"
    else:
        row["why_no_call"] = "failed before any model call"
    return row


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", required=True)
    ap.add_argument("--document", help="document id (prefix ok)")
    ap.add_argument("--file", help="image path, when there is no document row")
    ap.add_argument("--model", default="apple:apple-vision",
                    help="provider:model tried FIRST")
    ap.add_argument("--fallback-model",
                    default="openrouter:google/gemini-3.1-flash-lite",
                    help="provider:model tried when the first cannot do the job. "
                         "Apple's on-device stack is free and private but only "
                         "does OCR and text, so most vision tools land here — "
                         "which is the point of trying Apple first.")
    ap.add_argument("--all-tools", action="store_true",
                    help="include tools that call no model")
    ap.add_argument("--tools", help="comma-separated; default = every LLM tool "
                                    "that can take this input")
    ap.add_argument("--input", choices=("page", "content", "both"), default="page")
    ap.add_argument("--category", help="limit to one tool category, e.g. vision")
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--limit", type=int, default=0, help="stop after N tools")
    ap.add_argument("--prompts", action="store_true",
                    help="print every tool's prompt and exit — no model calls, "
                         "no cost, the whole registry in one page")
    ap.add_argument("--markdown", help="also write a readable report here: one "
                                       "section per tool, prompt and output in full")
    ap.add_argument("--assert-ok", action="store_true",
                    help="exit non-zero if any tool errored or answered without "
                         "calling the model")
    args = ap.parse_args()

    os.environ.setdefault("FICHERO_LIBRARY_PATH", args.library)

    import fichero_server.workflows.tools  # noqa: F401  registers everything
    from fichero_server.db import db_manager
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Document
    from fichero_server.workflows.registry import list_tools

    provider, _, model = args.model.partition(":")
    llm_config = LLMConfig(provider=provider, model=model)
    fallback_config = None
    if args.fallback_model and args.fallback_model != args.model:
        fb_provider, _, fb_model = args.fallback_model.partition(":")
        fallback_config = LLMConfig(provider=fb_provider, model=fb_model)

    document: dict[str, Any] = {}
    file_path = args.file or ""
    if args.document:
        db = db_manager.get_database(args.library)
        doc = db.get(Document, args.document)
        if doc is None:  # prefix
            matches = [d for d in db.query(Document)
                       if d.id.startswith(args.document)]
            if len(matches) != 1:
                print(f"--document {args.document!r} matched {len(matches)} rows")
                return 2
            doc = matches[0]
        document = doc.model_dump()
        file_path = file_path or document.get("path") or ""
    if not file_path:
        print("need --file or a --document with a path")
        return 2

    wanted = {t.strip() for t in args.tools.split(",")} if args.tools else None
    tools = [
        t for t in list_tools()
        if (wanted is None or t.name in wanted)
        and (args.category is None or t.category == args.category)
        and (args.all_tools or getattr(t, "uses_llm", False))
    ]
    tools.sort(key=lambda t: (t.category, t.name))

    if args.prompts:
        for t in tools:
            print(f"\n{'=' * 78}\n{t.name}  ({t.category})  —  "
                  f"{getattr(t, 'display_name', t.name)}\n{'=' * 78}")
            print(tool_prompt(t))
        print(f"\n{len(tools)} tools")
        return 0

    recorder = Recorder()
    recorder.install()
    state = {"input_files": [file_path], "library_path": args.library,
             "task_id": None}
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    try:
        for tool_def in tools:
            inputs = build_inputs(tool_def, mode=args.input,
                                  file_path=file_path, document=document)
            if inputs is None:
                skipped.append(tool_def.name)
                continue
            print(f"  → {tool_def.name} …", flush=True)
            row = await run_one(tool_def.name, tool_def, inputs, state,
                                llm_config, recorder,
                                document.get("page_content") or "")
            row["model_used"] = args.model
            # Apple first, then the fallback. A tool that Apple's on-device
            # stack cannot do (describe, classify, table) fails or answers
            # without calling anything, and that is not a verdict on the tool —
            # it is a verdict on the model. Ask the other one before judging.
            if fallback_config is not None and (
                not row["ok"] or not row["called_model"]
            ):
                retry = await run_one(tool_def.name, tool_def, inputs, state,
                                      fallback_config, recorder,
                                      document.get("page_content") or "")
                retry["model_used"] = args.fallback_model
                retry["first_model_verdict"] = (
                    row.get("error") or row.get("why_no_call") or "no answer"
                )
                if retry["ok"] and retry["called_model"]:
                    row = retry
                elif not row["ok"] and retry["ok"]:
                    row = retry
            rows.append(row)
            if args.limit and len(rows) >= args.limit:
                break
    finally:
        recorder.restore()

    report = {
        "library": args.library,
        "document_id": document.get("id"),
        "document_name": document.get("name"),
        "file": file_path,
        "model": args.model,
        "fallback_model": args.fallback_model,
        "input_mode": args.input,
        "page_content_chars": len(document.get("page_content") or ""),
        "skipped_wrong_input_kind": skipped,
        "results": rows,
    }

    print()
    print(f"{'tool':28} {'ok':>3} {'called':>6} {'secs':>6}  "
          f"{'model':18}  first line of output")
    print("-" * 118)
    for r in rows:
        head = (r["output"] or r.get("error") or "").strip().splitlines()
        model_tag = (r.get("model_used") or "").split(":")[-1][:18]
        print(f"{r['tool']:28} {'yes' if r['ok'] else 'NO':>3} "
              f"{'yes' if r['called_model'] else 'NO':>6} {r['seconds']:>6.1f}  "
              f"{model_tag:18}  {(head[0] if head else '')[:40]}")
    silent = [r for r in rows if r["ok"] and not r["called_model"]]
    if silent:
        print("\nAnswered WITHOUT calling the model:")
        for r in silent:
            print(f"  {r['tool']:24} {r['why_no_call']}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nreport: {args.out}")
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(report))
        print(f"report: {args.markdown}")
    if args.assert_ok:
        bad = [r["tool"] for r in rows
               if not r["ok"] or not r["called_model"]]
        if bad:
            print(f"\nFAILED: {', '.join(bad)}")
            return 1
    return 0


def render_markdown(report: dict) -> str:
    """One section per tool: what went in, the prompt, what came back.

    The point is to be readable without a JSON viewer — you skim the table,
    find the tool that looks wrong, and read its prompt right there.
    """
    out = [
        f"# Tool sweep — {report['document_name'] or report['file']}",
        "",
        f"- **model** `{report['model']}`",
        f"- **input mode** `{report['input_mode']}`",
        f"- **file** `{report['file']}`",
        f"- **page content** {report['page_content_chars']} chars",
        "",
        "| tool | ok | called model | secs | first line |",
        "|---|---|---|---|---|",
    ]
    for r in report["results"]:
        head = (r["output"] or r.get("error") or "").strip().splitlines()
        first = (head[0] if head else "").replace("|", "\\|")[:70]
        out.append(f"| `{r['tool']}` | {'yes' if r['ok'] else '**NO**'} | "
                   f"{'yes' if r['called_model'] else '**NO**'} | "
                   f"{r['seconds']:.1f} | {first} |")
    if report["skipped_wrong_input_kind"]:
        out += ["", "Skipped (cannot take this input kind): "
                + ", ".join(f"`{t}`" for t in report["skipped_wrong_input_kind"])]
    for r in report["results"]:
        out += ["", "---", "", f"## {r['tool']} — {r['display_name']}", ""]
        if r.get("error"):
            out += [f"**error:** `{r['error']}`", ""]
        out += ["**Prompt sent**", "", "```", 
                (r["model_calls"][0]["prompt"] if r["model_calls"]
                 else r["registered_prompt"] + "\n\n<< no model call was made >>"),
                "```", "", "**Output**", "", "```",
                (r["output"] or "")[:6000], "```"]
    return "\n".join(out) + "\n"



if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
