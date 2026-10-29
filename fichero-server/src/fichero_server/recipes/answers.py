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
    for key in ("jobs", "removed_jobs"):
        if key in out:
            out[key] = list(dict.fromkeys(_list(out[key])))
            unknown = [j for j in out[key] if j not in STEP_ORDER]
            if unknown:
                problems.append(f"Fichero has no job {', '.join(map(repr, unknown))}.")
    if "cloud_spend_cap_usd" in out:
        cap = out["cloud_spend_cap_usd"]
        if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0:
            problems.append("The cloud spending cap is a number of dollars, 0 or more.")
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
    job_answers = out.get("job_answers")
    if isinstance(job_answers, dict) and "normalise_how_far" in job_answers:
        levels, refused = normalise_levels(job_answers["normalise_how_far"])
        problems += refused
        out["job_answers"] = {**job_answers, "normalise_how_far": levels}
    if isinstance(job_answers, dict) and job_answers.get("review_lenses") is not None:
        from fichero_server.recipes.review_profiles import lens_ids

        unknown = [x for x in _list(job_answers["review_lenses"]) if x not in lens_ids()]
        if unknown:
            problems.append(f"A review lens is {', '.join(lens_ids())}; not {', '.join(map(repr, unknown))}.")
    if isinstance(job_answers, dict) and job_answers.get("review_instructions") is not None:
        from fichero_server.recipes.review_profiles import lens_ids

        said = job_answers["review_instructions"]
        if not isinstance(said, dict) or any(not isinstance(v, str) for v in said.values()):
            problems.append("A review's instructions are text for each lens, by the lens's name.")
        else:
            unknown = [k for k in said if k not in lens_ids()]
            if unknown:
                problems.append(f"A review lens is {', '.join(lens_ids())}; not {', '.join(map(repr, unknown))}.")
    if isinstance(job_answers, dict) and job_answers.get("leave_out") is not None and not isinstance(job_answers["leave_out"], bool):
        problems.append(f"Leave Out is yes or no, not {job_answers['leave_out']!r}.")
    if isinstance(job_answers, dict) and job_answers.get("review_certainty_bar") not in (None, "", "whole-page"):
        bar = job_answers["review_certainty_bar"]
        try:
            ok = not isinstance(bar, bool) and 0 < float(bar) <= 1
        except (TypeError, ValueError):
            ok = False
        if not ok:
            problems.append(f"The certainty under which a line goes to the second model is a number above 0 and up to "
                            f"1 (or the whole page), not {bar!r}.")
    cap = out.get(SPEND_CAP)
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0):
        problems.append(f"The Hugging Face spend cap is an amount in dollars a month, $0 or more, not {cap!r}.")
    if out.get(COPIES_STAY) is not None and not isinstance(out[COPIES_STAY], bool):
        problems.append(f"Whether working copies may stay on the cluster is yes or no, not {out[COPIES_STAY]!r}.")
    if out.get(CLUSTER) is not None and not isinstance(out[CLUSTER], str):
        problems.append(f"The project's cluster is one set up here, by its name, not {out[CLUSTER]!r}.")
    if strict and problems:
        raise ValueError(" ".join(problems))
    return out


#: The ruled money-and-place answers (#5769, ruled 2026-10-17).
SPEND_CAP = "hf_spend_cap_usd"
COPIES_STAY = "copies_may_stay_on_cluster"
#: The cluster the project binds its cluster steps to, by the name Set Up shows (`source.recipe.runs-on-binds-to-a-
#: target`, #4950): the recipe never names it, the project does.
CLUSTER = "cluster"


def spend_cap(answers: dict[str, Any] | None) -> float:
    """How much the project may spend on Hugging Face a month (`source.onboard.spend-cap`): $0 unless setup said more,
    so every paid offer stays an offer."""
    cap = (answers or {}).get(SPEND_CAP)
    return float(cap) if isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap > 0 else 0.0


def copies_may_stay(answers: dict[str, Any] | None) -> bool:
    """Whether downscaled working copies may stay on the cluster for re-runs (`source.onboard.copies-may-stay-on-cluster`):
    setup's answer, else what the project said about pages leaving this Mac."""
    from fichero_server.recipes import places

    a = answers or {}
    said = a.get(COPIES_STAY)
    # The cluster is a place of its own: copies stay there only if the app allows it, whatever the answer says.
    return places.allows("acenet") and (said if isinstance(said, bool) else bool(a.get("cloud_allowed")))


#: The levels "Translate or normalise › Into what" may ask for (#5660 item 1): the page model's reading levels a
#: person writes towards (#5651, #5653), in the order a reading cascades.
NORMALISE_LEVELS: tuple[str, ...] = ("as_written", "expanded", "regularised", "modernised")
#: Set Up's own words for them, where they are not the engine's spelling.
_SETUP_WORDS = {"abbreviations_expanded": "expanded", "normalised_spelling": "regularised",
                "normalized_spelling": "regularised"}
#: A translation asked beside them: `translation:<language tag>`.
TRANSLATION_PREFIX = "translation:"


def normalise_levels(value: Any) -> tuple[list[str], list[str]]:
    """(the levels asked, in cascade order, then any translations; the problems in words). "Into what" is a list: a
    project saved with one value (`"normalised"`) reads as a list of one. Each level is spelled the engine's way
    (`as-written` -> `as_written`, `normalised` -> `regularised`); a translation is `translation:<tag>`, its
    language resolved to its tag. A value Fichero does not know is kept and named as a problem."""
    from fichero_server.models.readings import canonical_reading_level
    from fichero_server.recipes.names import resolve_language

    levels: list[str] = []
    translations: list[str] = []
    problems: list[str] = []
    for item in _list(value):
        text = str(item).strip()
        if text.lower().startswith(TRANSLATION_PREFIX):
            try:
                translations.append(TRANSLATION_PREFIX + resolve_language(text[len(TRANSLATION_PREFIX):]))
            except ValueError as exc:
                problems.append(str(exc))
                translations.append(text)
            continue
        level = canonical_reading_level(text)
        level = _SETUP_WORDS.get(level or "", level)
        if level not in NORMALISE_LEVELS:
            problems.append(f"Fichero has no level {text!r} to normalise into; choose from as written, "
                            "abbreviations expanded, normalised spelling or modernised.")
            levels.append(text)
            continue
        levels.append(level)
    ordered = [lv for lv in NORMALISE_LEVELS if lv in levels] + [lv for lv in levels if lv not in NORMALISE_LEVELS]
    return list(dict.fromkeys(ordered + translations)), problems


#: Each reading level's title, as Set Up and the Start plan name its run.
NORMALISE_TITLES = {"as_written": "As written", "expanded": "Abbreviations expanded",
                    "regularised": "Normalised spelling", "modernised": "Modernised"}


def normalise_run_titles(target: Any) -> list[str]:
    """The Normalise step's runs by title, in the order Start makes them (`recipes/start.py`, #5795): one for each level
    asked, one for a translation ("Translation into English"); nothing asked writes regularised, and a level Fichero
    does not know has no run, so no title."""
    from fichero_server.recipes.names import language_name

    asked, _ = normalise_levels(target or ["regularised"])
    return [f"Translation into {language_name(t[len(TRANSLATION_PREFIX):])}" if t.startswith(TRANSLATION_PREFIX)
            else NORMALISE_TITLES[t] for t in asked if t.startswith(TRANSLATION_PREFIX) or t in NORMALISE_TITLES]
