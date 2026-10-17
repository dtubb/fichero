"""Timecoded transcripts (#975): .srt / .vtt / .sbv and whisper/pyannote-style segment JSON.

Each cue becomes {start_ms, end_ms, speaker?, text}; the dialog alone (no
timestamps, cue numbers or markup) is the document's page_content.
"""
from __future__ import annotations

import json
import re

TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".sbv"}

_TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
_SRT_VTT_CUE = re.compile(rf"{_TIME}\s*-->\s*{_TIME}")
_SBV_CUE = re.compile(rf"^{_TIME},{_TIME}\s*$")
_VOICE = re.compile(r"<v\s+([^>]+)>")
_TAG = re.compile(r"</?[^>]+>")
_SPEAKER = re.compile(r"^([A-Z][A-Z0-9 _-]{1,30}):\s+(.*)$")


def _ms(h, m, s, frac) -> int:
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def _segment(start_ms: int, end_ms: int, lines: list[str]) -> dict | None:
    raw = "\n".join(lines)
    voice = _VOICE.search(raw)
    speaker = voice.group(1).strip() if voice else None
    text = " ".join(_TAG.sub("", raw).split())
    if not speaker:
        said = _SPEAKER.match(text)
        if said:
            speaker, text = said.group(1), said.group(2)
    if not text:
        return None
    seg = {"start_ms": start_ms, "end_ms": end_ms}
    if speaker:
        seg["speaker"] = speaker
    seg["text"] = text
    return seg


def _parse_json(text: str) -> list[dict]:
    data = json.loads(text)
    items = data.get("segments") if isinstance(data, dict) else data
    out = []
    for item in items or []:
        if not isinstance(item, dict) or "start" not in item:
            continue
        seg = {"start_ms": round(float(item["start"]) * 1000), "end_ms": round(float(item.get("end", item["start"])) * 1000)}
        if item.get("speaker"):
            seg["speaker"] = str(item["speaker"])
        seg["text"] = str(item.get("text", "")).strip()
        if seg["text"]:
            out.append(seg)
    return out


def parse_transcript(text: str, suffix: str) -> list[dict]:
    """Segments of a transcript file's text; ``suffix`` picks the format."""
    if suffix == ".json":
        return _parse_json(text)
    segments: list[dict] = []
    cue: tuple[int, int] | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal cue, lines
        if cue is not None:
            seg = _segment(cue[0], cue[1], lines)
            if seg:
                segments.append(seg)
        cue, lines = None, []

    for line in text.lstrip("﻿").splitlines():
        stripped = line.strip()
        m = _SBV_CUE.match(stripped) if suffix == ".sbv" else _SRT_VTT_CUE.search(stripped)
        if m:
            flush()
            g = m.groups()
            cue = (_ms(*g[0:4]), _ms(*g[4:8]))
        elif not stripped:
            flush()
        elif cue is not None:
            lines.append(stripped)
    flush()
    return segments


def transcript_text(segments: list[dict]) -> str:
    return "\n".join(s["text"] for s in segments)
