"""#975: subtitle files ingest as timecoded segments with clean dialog as page_content."""
from __future__ import annotations

import asyncio
import json

from fichero_server.loaders.document_loader import DocumentLoader
from fichero_server.loaders.transcript_loader import parse_transcript

SRT = """1
00:00:01,000 --> 00:00:03,500
<i>Good morning.</i>

2
00:01:02,250 --> 00:01:04,000
SPEAKER 1: Shall we begin?
"""

VTT = """WEBVTT

NOTE a comment

00:01.000 --> 00:03.500
<v Ana>Good morning.</v>

01:00:02.250 --> 01:00:04.000 align:start
Shall we begin?
"""

SBV = """0:00:01.000,0:00:03.500
Good morning.

0:01:02.250,0:01:04.000
Shall we begin?
"""


def test_srt_segments_and_speaker():
    segs = parse_transcript(SRT, ".srt")
    assert segs[0] == {"start_ms": 1000, "end_ms": 3500, "text": "Good morning."}
    assert segs[1] == {"start_ms": 62250, "end_ms": 64000, "speaker": "SPEAKER 1", "text": "Shall we begin?"}


def test_vtt_voice_tag_short_and_hour_timestamps():
    segs = parse_transcript(VTT, ".vtt")
    assert segs[0] == {"start_ms": 1000, "end_ms": 3500, "speaker": "Ana", "text": "Good morning."}
    assert (segs[1]["start_ms"], segs[1]["end_ms"]) == (3_602_250, 3_604_000)


def test_sbv():
    assert [s["start_ms"] for s in parse_transcript(SBV, ".sbv")] == [1000, 62250]


def test_diarization_json():
    data = json.dumps({"segments": [{"start": 1.0, "end": 2.5, "speaker": "SPEAKER_00", "text": " Hello "}]})
    assert parse_transcript(data, ".json") == [
        {"start_ms": 1000, "end_ms": 2500, "speaker": "SPEAKER_00", "text": "Hello"}
    ]


def test_loader_gives_clean_text_and_a_transcript_artifact(tmp_path):
    path = tmp_path / "talk.srt"
    path.write_text(SRT)
    content = asyncio.run(DocumentLoader().load(path))
    assert content.text == "Good morning.\nShall we begin?"
    (payload,) = content.metadata["_kreuzberg_artifacts"]
    assert payload["artifact_type"] == "transcript"
    assert len(payload["data"]["segments"]) == 2


def test_plain_text_transcripts_stay_flat(tmp_path):
    path = tmp_path / "talk.txt"
    path.write_text("00:00:01 hello\n")
    content = asyncio.run(DocumentLoader().load(path))
    assert content.text == "00:00:01 hello\n"
    assert "_kreuzberg_artifacts" not in content.metadata
