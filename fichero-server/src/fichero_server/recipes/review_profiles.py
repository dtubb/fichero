"""The review is built from the project and a profile (`source.job.review-is-built-from-the-project-and-a-profile`, #5723).

A profile is a data file in `seed/review-profiles/` (what is particular to a language, script, period and hand) and
a lens is one pass of the review (abbreviations, orthography, names and dates). The prompt a review node sends is the
shared frame, the project's facts (its setup answers), the chosen profile's context and the node's lens. No language,
script or direction is named here: a new one is a new file. A profile is chosen by the rules that choose a reader card
(`assemble._refusal`: language, script, material, period), and a project no profile is made for gets the generic one,
and is told so.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

SEED = Path(__file__).parent / "seed" / "review-profiles"
GENERIC = "generic"


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    status: str
    card: Any  # an `assemble.Card` holding the profile's `suits`, so the reader-card rules read it
    context: str
    lenses: dict[str, dict[str, str]]


def _one(text: Any) -> str:
    return " ".join(str(text).split())


@lru_cache(maxsize=1)
def frame() -> dict[str, Any]:
    import yaml

    return yaml.safe_load((SEED / "_frame.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def profiles() -> dict[str, Profile]:
    """Every shipped profile by id. A file that is malformed, or whose lenses are not the generic profile's,
    raises: a profile with a lens missing would be reviewed through nothing."""
    import yaml

    from fichero_server.recipes.assemble import Card

    out: dict[str, Profile] = {}
    for path in sorted(SEED.glob("[!_]*.yaml")):
        row = yaml.safe_load(path.read_text(encoding="utf-8"))
        if row.get("id") != path.stem:
            raise ValueError(f"{path.name}: its id is {row.get('id')!r}; a profile's id is its file name")
        suits = row.get("suits") or {}
        card = Card(id=row["id"], pin={}, jobs=frozenset({"correct"}),
                    scripts=frozenset(suits["scripts"]) if suits.get("scripts") else None,
                    languages=frozenset(suits["languages"]) if suits.get("languages") else None,
                    material=frozenset(suits.get("material") or ()),
                    period=tuple(suits["period"]) if suits.get("period") else None)
        out[row["id"]] = Profile(row["id"], row["title"], row.get("status", "shipped"), card,
                                 _one(row["context"]), dict(row["lenses"]))
    if GENERIC not in out:
        raise ValueError(f"{SEED}: the {GENERIC!r} profile is missing; a project no profile fits is reviewed by it")
    wanted = set(out[GENERIC].lenses)
    for profile in out.values():
        if set(profile.lenses) != wanted:
            raise ValueError(f"profile {profile.id!r} has lenses {sorted(profile.lenses)}; "
                             f"every profile has {sorted(wanted)}")
    return out


def lens_ids() -> list[str]:
    return list(profiles()[GENERIC].lenses)


#: The shipped review preset a recipe's Correct step runs (`start.WORKFLOW_FOR_JOB["correct"]`).
REVIEW_PRESET = "transcribe_paleography_review"
#: The name a run made before the rename carries as its `workflow` (#6128), read as the preset it became.
RENAMED = {"Paleographer Review": "Review the Reading"}


def review_passes(preset: str, lenses: list[str] | None) -> int | None:
    """The model calls a page takes in the shipped review preset `preset` (its key, or the name a run carries as its
    `workflow`) with `lenses` on (None: every lens): one for each pass `keep_lenses` keeps (#5723), so 0 with every
    lens off; 1 for a preset with no review pass (one call a page, review 163). None only when the preset cannot be
    read: unpriced, never a $0 review (#5590, review 160)."""
    import json

    from fichero_server.workflows.default_workflows import _PRESETS_DIR, shipped_preset

    preset = RENAMED.get(preset, preset)
    found = shipped_preset(preset)
    if found is None:
        for path in sorted(_PRESETS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("name") == preset:
                found = data
                break
    if not found:
        return None
    nodes = found.get("nodes") or []
    if not any(node.get("tool") == "transcribe_review" for node in nodes):
        return 1
    kept, _ = keep_lenses(nodes, found.get("edges") or [], lens_ids() if lenses is None else lenses)
    return sum(1 for node in kept if node.get("tool") == "transcribe_review")


def keep_lenses(nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                lenses: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A review workflow with only `lenses` on (#5723): a pass through several lenses keeps those on; a pass whose
    lens is off leaves, and what fed its `context` feeds the pass after it; a node that fed only passes that left
    goes too. Unchanged when every lens of the workflow is on. ponytail: it assumes today's chain shape, each pass
    taking the one before through `context` and giving `records`, and rewires only those two ports; a preset that
    chains its passes another way needs its own rule here."""
    on = set(lenses)
    kept, gone = [], set()
    for node in nodes:
        lens = (node.get("config") or {}).get("lens") if node.get("tool") == "transcribe_review" else None
        if not lens:
            kept.append(node)
            continue
        mine = [x for x in lens.split(",") if x.strip() in on]
        if not mine:
            gone.add(node["id"])
        elif len(mine) < len(lens.split(",")):
            kept.append({**node, "config": {**node["config"], "lens": ",".join(m.strip() for m in mine)}})
        else:
            kept.append(node)
    if not gone:
        return kept, edges
    wired = list(edges)
    for node in [n["id"] for n in nodes if n["id"] in gone]:  # in order, so two passes off in a row chain too
        # chain around it: what fed its context feeds whoever took its records
        into = [e for e in wired if e["target"] == node and e.get("target_port") == "context"]
        out = [e for e in wired if e["source"] == node and e.get("source_port") == "records"]
        wired = [e for e in wired if node not in (e["source"], e["target"])]
        wired += [{**o, "id": f"{i['source']}-{o['target']}-context", "source": i["source"],
                   "source_port": i["source_port"]} for i in into for o in out]
    fed, fed_by = {e["source"] for e in edges}, {e["target"] for e in edges}
    while True:  # a helper (a search) that fed only passes that left, or was fed only by them
        feeds, takes = {e["source"] for e in wired}, {e["target"] for e in wired}
        idle = {n["id"] for n in kept if n.get("tool") != "transcribe_review"
                and ((n["id"] in fed and n["id"] not in feeds) or (n["id"] in fed_by and n["id"] not in takes))}
        if not idle:
            break
        gone |= idle
        kept = [n for n in kept if n["id"] not in idle]
        wired = [e for e in wired if e["source"] not in idle and e["target"] not in idle]
    return kept, wired


def _answers(raw: dict[str, Any] | None) -> Any:
    from fichero_server.recipes.answers import normalise
    from fichero_server.recipes.assemble import Answers

    a = normalise(raw, strict=False) or {}
    return Answers(languages=frozenset(a.get("languages") or ()), scripts=frozenset(a.get("scripts") or ()),
                   materials=tuple(a.get("materials") or ()), period=str(a.get("period") or ""))


def _fits(profile: Profile, a: Any) -> bool:
    """The reader-card rules (`assemble._refusal`) for a profile: its card must list the project's languages and
    scripts, state its material, and not state a period that misses the project's. A profile that states a language
    does not fit a project that states none."""
    from fichero_server.recipes.assemble import in_period

    card = profile.card
    if card.languages is not None and not (a.languages and a.languages <= card.languages):
        return False
    if card.scripts is not None and a.scripts and not a.scripts <= card.scripts:
        return False
    if card.material and a.material not in card.material:
        return False
    return in_period(card, a) is not False


def _span(profile: Profile) -> int:
    """The years a profile's period covers: of two that fit, the narrower is the nearer to the project's date."""
    period = profile.card.period
    return period[1] - period[0] if period else 10**6


def choose(answers: dict[str, Any] | None) -> tuple[Profile, str]:
    """The profile for the project's setup answers, and a sentence saying which and why. Among those that fit, the
    one whose period states the project's, then by id; the generic profile when no other fits, said in words and
    never replaced by a profile made for another language."""
    from fichero_server.recipes.assemble import in_period
    from fichero_server.recipes.names import language_name

    a = _answers(answers)
    fitting = sorted((p for p in profiles().values() if p.id != GENERIC and _fits(p, a)),
                     key=lambda p: (in_period(p.card, a) is not True, _span(p) if in_period(p.card, a) else 0, p.id))
    if fitting:
        best = fitting[0]
        stub = (" It is a stub: it says what makes the hand hard, not yet the genres and spellings."
                if best.status == "stub" else "")
        return best, f"Reviewed with the profile “{best.title}”.{stub}"
    named = ", ".join(language_name(t) for t in sorted(a.languages)) or "no language"
    when = f", {a.period}" if a.period else ""
    return profiles()[GENERIC], f"No review profile is made for {named}{when}: the generic review is used."


def facts(answers: dict[str, Any] | None) -> str:
    """The project's stated facts as one sentence for the prompt; '' when it states none."""
    from fichero_server.recipes.answers import normalise
    from fichero_server.recipes.names import language_name, script_name

    a = normalise(answers, strict=False) or {}
    parts = []
    if a.get("languages"):
        parts.append("language: " + ", ".join(language_name(t) for t in a["languages"]))
    if a.get("scripts"):
        parts.append("script: " + ", ".join(script_name(c) for c in a["scripts"]))
    directions = a.get("directions") or {}
    words = frame()["directions"]
    said = [words[d] for d in dict.fromkeys(directions.values() if isinstance(directions, dict) else directions)
            if d in words]
    if said:
        parts.append("; ".join(said))
    for key, label in (("period", "written about"), ("place", "place"), ("hand", "hand")):
        if a.get(key):
            parts.append(f"{label}: {a[key]}")
    if a.get("materials"):
        parts.append("material: " + ", ".join(a["materials"]))
    return ("The project states: " + "; ".join(parts) + ".") if parts else ""


def line_scripts(lines: list[tuple[str, str | None, str | None]]) -> str:
    """For a page whose lines state different scripts or directions, each line's own, from its segment
    (`source.recipe.nothing-assumes-spaces-direction-or-an-alphabet`, #5728): `lines` is (segment id, script,
    direction) in reading order. '' for a page of one script, which the project's facts already say."""
    from fichero_server.recipes.names import script_name

    if len({(script, direction) for _id, script, direction in lines if script}) < 2:
        return ""
    words = frame()["directions"]
    said = [f"- {segment_id}: {script_name(script) if script else 'script not stated'}"
            + (f", {words[direction]}" if direction in words else "") for segment_id, script, direction in lines]
    return ("This page mixes scripts: read each line in its own script and direction, as listed, never the project's "
            "one script for the whole page:\n" + "\n".join(said))


def review_prompt(lens: str, answers: dict[str, Any] | None) -> tuple[str, str]:
    """(the prompt a review node sends through `lens`, the sentence saying which profile it was built from).
    Raises for a lens no profile has."""
    profile, said = choose(answers)
    names = [name.strip() for name in lens.split(",") if name.strip()]  # "a,b": one pass through several lenses
    for name in names or [lens]:
        if name not in profile.lenses:
            raise ValueError(f"there is no review lens {name!r}; the lenses are {', '.join(lens_ids())}")
    chosen = [profile.lenses[name] for name in names]
    shared = frame()
    parts = [_one(shared["intro"]), facts(answers), profile.context,
             f"**This pass: {'; '.join(c['title'] for c in chosen)}.**\n"
             + "\n".join(c["text"].rstrip() for c in chosen), _one(shared["closing"]),
             "Output the COMPLETE corrected transcription (same line breaks), nothing else."]
    return "\n\n".join(p for p in parts if p), said
