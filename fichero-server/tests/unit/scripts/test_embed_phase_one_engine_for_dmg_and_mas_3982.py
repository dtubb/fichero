"""DMG and MAS embed the same engine (`engine.dmg-mas-byte-identical-guard`, #3982).

Both channels are build CONFIGURATIONS of one `Fichero` target, so they share one
"Embed Fichero Server" phase. They embed the same bytes as long as that phase has a single
source path that no configuration or channel flag can steer. This pins that: one phase, one
unconditional `ENGINE_SRC`, no branch on the channel. A future edit that gives the App Store
build its own source (or its own phase) fails here instead of shipping two engines.
"""
from __future__ import annotations

import re
from pathlib import Path

PBXPROJ = Path(__file__).resolve().parents[4] / "fichero/fichero.xcodeproj/project.pbxproj"
_CHANNEL = re.compile(r"FICHERO_APP_STORE|CONFIGURATION\b|\$\{?CONFIGURATION")


def _phase(text: str) -> str:
    """The shell script of the single embed phase, as one string."""
    blocks = re.findall(r'/\* Embed Fichero Server \*/ = \{.*?\n\t\t\};', text, re.S)
    assert len(blocks) == 1, f"expected exactly one embed phase, found {len(blocks)}"
    return blocks[0]


def _problems(text: str) -> list[str]:
    phase = _phase(text)
    out = []
    srcs = re.findall(r'"ENGINE_SRC=\\"([^"]*?)\\""', phase)
    if len(srcs) != 1:
        out.append(f"ENGINE_SRC assigned {len(srcs)} times, want 1")
    shell = phase[phase.index("shellScript"):]
    if _CHANNEL.search(shell):
        out.append("embed script branches on the channel/configuration")
    return out


def test_dmg_and_mas_share_one_unconditional_engine_source():
    assert _problems(PBXPROJ.read_text()) == []


def test_it_catches_a_channel_specific_source():
    text = PBXPROJ.read_text()
    bad = text.replace('"ENGINE_SRC=', '"if [ \\"$CONFIGURATION\\" = AppStore ]; then ENGINE_SRC=other; fi",\n\t\t\t\t"ENGINE_SRC=', 1)
    assert _problems(bad), "detector missed a configuration-dependent ENGINE_SRC"
