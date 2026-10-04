"""What setup works out instead of asking (`source.onboard.derives-not-asks`).

For the scripts a person picked: each script's direction (the language policy's own rule) and
whether it may be vertical (which only the pages can settle, so setup asks); the bundled font that
covers a script macOS lacks; this Mac's chip and memory; which providers have a key (names only);
and the places work can run. Every fact says where it came from, so setup can show it and the
person can correct it. Nothing here is new knowledge: each fact is read from the engine's existing
source for it.
"""
from __future__ import annotations

import platform
import subprocess
from typing import Any

#: ISO 15924 codes each bundled font covers (`api/routes/system/fonts.py`, in fallback order).
FONT_SCRIPTS: dict[str, tuple[str, ...]] = {
    "Junicode": ("Latn", "Latf"),
    "Noto Sans Syriac": ("Syrc", "Syre"),
    "Noto Sans Syriac Western": ("Syrj",),
    "Noto Sans Syriac Eastern": ("Syrn",),
    "Noto Sans Mongolian": ("Mong",),
    "Noto Sans Coptic": ("Copt",),
    "Noto Sans Cherokee": ("Cher",),
}
#: Scripts the system fonts already draw; Junicode is only their fallback for MUFI letters.
_SYSTEM_DRAWS = frozenset({"Latn", "Latf"})


def unknown_scripts(codes: list[str]) -> list[str]:
    from fichero_server.recipes.names import _scripts

    known = {row["code"] for row, _text in _scripts()}
    return [c for c in codes if c not in known]


def script_facts(code: str) -> dict[str, Any]:
    from fichero_server.llm.language_policy import resolve_direction, script_may_be_vertical

    direction = resolve_direction(script=code)
    font = next((f for f, scripts in FONT_SCRIPTS.items() if code in scripts and code not in _SYSTEM_DRAWS), None)
    return {
        "script": code,
        "direction": direction.language,
        "direction_from": direction.basis,
        "may_be_vertical": script_may_be_vertical(code),
        "font": font,
        "font_from": f"Fichero's bundled {font} (SIL OFL)" if font else "the system font draws it",
    }


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=5,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def this_mac() -> dict[str, Any]:
    memory = _sysctl("hw.memsize")
    return {
        "chip": _sysctl("machdep.cpu.brand_string") or platform.machine(),
        "memory_gb": round(int(memory) / 2**30) if memory and memory.isdigit() else None,
        "from": "this Mac's own report (sysctl)",
    }


def _providers_with_keys() -> list[str]:
    """Catalog providers that need a key and have one the engine can read; names only."""
    from fichero_server.llm import get_api_key
    from fichero_server.llm.providers import PROVIDERS

    return [p.value for p, info in PROVIDERS.items()
            if info.api_key_env and not info.is_local and get_api_key(p.value)]


def targets(keys: list[str], clusters: list[str]) -> list[dict[str, str]]:
    found = [{"id": "this-mac", "title": "This Mac", "from": "always"}]
    if "huggingface" in keys:
        found.append({"id": "huggingface", "title": "Hugging Face Jobs", "from": "a Hugging Face key is present"})
    found += [{"id": f"cluster:{c}", "title": c, "from": "a configured HPC cluster"} for c in clusters]
    return found
