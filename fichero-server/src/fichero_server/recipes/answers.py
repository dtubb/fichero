"""Setup's answers in the one shape the engine keeps them (section 7b, #5478, #5479).

`purposes` and `materials` are lists (checkboxes, any mix); `languages` are tags and `scripts` ISO
15924 codes, never the typed word; `directions` holds one direction per script, defaulted from the
script. A project saved before 2026-10-05 has a single `purpose` and `material`: they read as a list
of one, nothing lost. Two strengths:

- `strict` (saving, assembling): a word that is not a tag is resolved to its tag when exactly one
  language has that name, and otherwise refused in words; so is an unknown purpose, material, job
  or direction.
- lenient (reading what a project already holds): the same conversion, but a value it cannot
  resolve is kept as it was, so reading never fails and never loses an answer.
"""
from __future__ import annotations

from typing import Any

#: The directions setup offers (section 7b, screen 4): left to right, right to left, top to bottom
#: with columns right to left (`ttb`), and top to bottom with columns left to right (`ttb-lr`).
SETUP_DIRECTIONS: tuple[str, ...] = ("ltr", "rtl", "ttb", "ttb-lr")


def _list(value: Any) -> list:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


#: Scripts whose historical material is written in columns, and the way the columns run (ruled 2026-09-28, #5173:
#: Mongolian columns left to right, Chinese and Japanese right to left). Simplified Han and Korean stay `ltr`: their
#: material is mostly modern and horizontal. A person changes any of them in setup (#5595).
VERTICAL_BY_DEFAULT: dict[str, str] = {"Mong": "ttb-lr", "Phag": "ttb-lr", "Hani": "ttb", "Hant": "ttb",
                                       "Jpan": "ttb", "Hira": "ttb", "Kana": "ttb"}


def default_direction(script: str) -> str:
    """The direction the script is written in: a vertical script's columns (`VERTICAL_BY_DEFAULT`), else as the
    language policy derives it."""
    from fichero_server.recipes.derived import script_facts

    if script in VERTICAL_BY_DEFAULT:
        return VERTICAL_BY_DEFAULT[script]
    direction = script_facts(script)["direction"]
    return direction if direction in SETUP_DIRECTIONS else "ltr"


def normalise(raw: dict[str, Any] | None, *, strict: bool) -> dict[str, Any] | None:
    """The answers with `purposes`, `materials`, tag `languages`, code `scripts` and `directions`.
    Raises ValueError, in words, only when `strict`."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        if strict:
            raise ValueError("Setup's answers are a mapping of question to answer.")
        return raw
    from fichero_server.recipes.assemble import MATERIALS, PURPOSES, STEP_ORDER
    from fichero_server.recipes.names import resolve_language, resolve_script

    out = dict(raw)
    problems: list[str] = []

    def keep_or_refuse(value: Any, resolve) -> Any:
        try:
            return resolve(str(value))
        except ValueError as exc:
            problems.append(str(exc))
            return value

    purposes = _list(out.pop("purposes", None)) + _list(out.pop("purpose", None))
    # None ticked is "Not sure yet"; "Not sure yet" beside a ticked purpose says nothing more.
    purposes = list(dict.fromkeys(purposes))
    out["purposes"] = [p for p in purposes if p != "not-sure"] or ["not-sure"]
    unknown = [p for p in out["purposes"] if p not in PURPOSES]
    if unknown:
        problems.append(f"Fichero has no purpose {', '.join(map(repr, unknown))}; "
                        f"choose from {', '.join(PURPOSES)}.")
    materials = _list(out.pop("materials", None)) + _list(out.pop("material", None))
    unknown = [m for m in materials if m not in MATERIALS]
    if unknown:
        problems.append(f"Material is handwriting, print, typescript or text (already text), not {', '.join(map(repr, unknown))}.")
    out["materials"] = [m for m in MATERIALS if m in materials] + unknown or ["handwriting"]
    if "languages" in out:
        out["languages"] = list(dict.fromkeys(keep_or_refuse(v, resolve_language) for v in _list(out["languages"])))
    if "scripts" in out:
        out["scripts"] = list(dict.fromkeys(keep_or_refuse(v, resolve_script) for v in _list(out["scripts"])))
    if "jobs" in out:
        out["jobs"] = list(dict.fromkeys(_list(out["jobs"])))
        unknown = [j for j in out["jobs"] if j not in STEP_ORDER]
        if unknown:
            problems.append(f"Fichero has no job {', '.join(map(repr, unknown))}.")
    chosen = dict(out.get("directions") or {})
    bad = {s: d for s, d in chosen.items() if d not in SETUP_DIRECTIONS}
    if bad:
        problems.append("A direction is " + ", ".join(SETUP_DIRECTIONS) + "; not "
                        + ", ".join(f"{d!r} for {s}" for s, d in bad.items()) + ".")
    scripts = [s for s in out.get("scripts") or [] if isinstance(s, str)]
    if scripts or chosen:
        from fichero_server.recipes.derived import unknown_scripts

        known = [s for s in scripts if not unknown_scripts([s])]
        out["directions"] = {s: chosen.get(s) or default_direction(s) for s in known}
    if strict and problems:
        raise ValueError(" ".join(problems))
    return out
