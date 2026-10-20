"""The bake-off's winning reads as training lines, and their only way out: a PRIVATE Hugging Face dataset (#5894;
`compute.tune.bakeoff-reads-become-training-lines`, `compute.tune.training-data-goes-only-to-a-private-dataset`).

`winning_lines` reads the harness's `lines.json` (`scripts/ab_kraken_cloud.py`), `stage_dataset` cuts each line's picture
the way the teacher read it and writes `pairs.jsonl` into a folder OUTSIDE the repository checkout, and
`push_private_dataset` sends that folder to a private dataset of the person's own account, after every refusal. Nothing here
starts a Job or a paid read. `HfApi` is the only boundary: tests replace it.
"""
from __future__ import annotations

import json
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PAIRS = "pairs.jsonl"
LINES_DIR = "lines"


class PublicDatasetRefused(RuntimeError):
    """The dataset is, or came back, public: nothing of the person's test pages goes to a public repository."""


class NotYourNamespace(RuntimeError):
    """The dataset is named under an account that is not the token's own."""


class NotConfirmed(RuntimeError):
    """The person's yes did not name the number of lines about to leave this Mac."""


#: The dataset card: what these lines are, so nobody takes a model's reading for a person's check.
CARD = """---
license: other
private: true
---
# Lines read by a model, not checked by a person

{count} line pictures with the text of `{winner}`, kept only where every reader that answered ({arms}) agreed. The text is
a **model reading, not checked by a person and not ground truth** (`checked_by_person: false` on every row). Lines left out:
{left}. For training only; this dataset is private and is not to be released.
"""


@dataclass
class WinningLine:
    page: str
    line_id: str
    polygon: list
    text: str
    read_by: str
    agreed_by: list[str]
    checked_by_person: bool = False  # a model's reading, never a person's check (`compute.tune.bootstrapped-data-is-marked`)


@dataclass
class Winning:
    lines: list[WinningLine]
    left_out: dict[str, int] = field(default_factory=dict)


@dataclass
class Staged:
    path: Path
    count: int
    files: list[str] = field(default_factory=list)  # exactly what stage_dataset wrote, relative to `path`: all that is uploaded


@dataclass
class Pushed:
    repo_id: str
    lines: int


def winning_lines(lines_json: str | Path, *, winner: str) -> Winning:
    """The winner's text for each line where every reader that answered agrees; the rest are counted, not used."""
    path = Path(lines_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    arms = data["arms"]
    if winner not in arms:
        raise ValueError(f"{winner!r} is not an arm in {path} ({', '.join(arms)})")
    kept: list[WinningLine] = []
    left = Counter()
    for row in data["lines"]:
        if "agreement" not in row:
            raise ValueError(f"{path} has no agreement: it takes three or more readers to say which lines are probably right")
        text = (row.get(winner) or "").strip()
        if not text:
            left["empty"] += 1
        elif row["agreement"] is None:
            left["fewer_than_two_readers"] += 1
        elif row["agreement"] == "split":
            left["split"] += 1
        else:
            kept.append(WinningLine(page=row["page"], line_id=str(row["id"]), polygon=row["polygon"], text=text,
                                    read_by=winner, agreed_by=[a for a in arms if a != "A" and (row.get(a) or "").strip()]))
    return Winning(kept, dict(left))


def drop_lines_a_person_checked(winning: Winning, pages_dir: str | Path, person_keys: set[str]) -> Winning:
    """The bake-off's staged lines without those a person already chose or typed (`source.compare.pick-is-a-training-line`):
    a line in both sets is the person's, kept once. Matched by `line_key` (page picture bytes and the line's polygon in
    whole pixels). The count of lines dropped is in `left_out["also_a_persons_line"]`."""
    from fichero_server.training.line_key import image_digest, line_key

    digests: dict[str, str] = {}
    kept: list[WinningLine] = []
    for line in winning.lines:
        if line.page not in digests:
            digests[line.page] = image_digest(Path(pages_dir) / line.page)
        if line_key(digests[line.page], line.polygon) not in person_keys:
            kept.append(line)
    dropped = len(winning.lines) - len(kept)
    left = dict(winning.left_out)
    if dropped:
        left["also_a_persons_line"] = left.get("also_a_persons_line", 0) + dropped
    return Winning(kept, left)


def _git_work_tree_above(path: Path) -> Path | None:
    """The nearest folder at or above `path` that is a git work tree (it has a .git, a folder or a worktree's file)."""
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent
    return None


def stage_dataset(winning: Winning, pages_dir: str | Path, out_dir: str | Path) -> Staged:
    """Line pictures (`line_cut.crop_line`, the teacher's own cut), `pairs.jsonl` and the dataset card in `out_dir`, which
    may not be inside ANY git work tree: material from the owner's test pages is never written where `git add` could take it."""
    from PIL import Image

    from fichero_server.llm.line_cut import crop_line

    out = Path(out_dir).expanduser().resolve()
    if (tree := _git_work_tree_above(out)) is not None:
        raise ValueError(f"{out} is inside the git work tree {tree}: stage the dataset outside every repository")
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} is not empty: stage into a new or empty folder, so only what was staged can be uploaded")
    (out / LINES_DIR).mkdir(parents=True, exist_ok=True)
    written = [PAIRS, "README.md"]
    with ExitStack() as stack, (out / PAIRS).open("w", encoding="utf-8") as pairs:
        pages: dict[str, Any] = {}
        for number, line in enumerate(winning.lines, 1):
            if line.page not in pages:
                pages[line.page] = stack.enter_context(Image.open(Path(pages_dir) / line.page))
            # By number, never by page name: `allow_patterns` are globs, and a name with [ ] * ? would not match itself.
            name = f"{LINES_DIR}/{number:05d}.jpg"
            crop_line(pages[line.page], line.polygon).save(out / name, format="JPEG", quality=90)
            written.append(name)
            pairs.write(json.dumps({"image": name, "text": line.text, "read_by": line.read_by, "agreed_by": line.agreed_by,
                                    "checked_by_person": line.checked_by_person}, ensure_ascii=False) + "\n")
    arms = sorted({a for line in winning.lines for a in line.agreed_by})
    (out / "README.md").write_text(CARD.format(count=len(winning.lines), winner=winning.lines[0].read_by if winning.lines else "?",
                                               arms=", ".join(arms) or "none", left=json.dumps(winning.left_out)), encoding="utf-8")
    return Staged(out, len(winning.lines), written)


def push_private_dataset(staged: Staged, repo_id: str, *, token: str, confirmed_lines: int | None,
                         api: Any | None = None) -> Pushed:
    """Send a staged folder to a private dataset. Every refusal comes first and nothing leaves until all have passed: no
    token, a token that may not write, a dataset that exists and is public, one that is not private once created, or a
    yes that does not name the number of lines. The dataset is created private and there is no way to ask otherwise."""
    from fichero_server.training.hf_jobs import HuggingFaceTokenRejected, NoHuggingFaceToken, _lacks

    if not token:
        raise NoHuggingFaceToken("No Hugging Face token: add one in Settings (AI providers, Hugging Face). It needs "
                                 "permission to write to your repositories.")
    if confirmed_lines != staged.count:
        raise NotConfirmed(f"{staged.count} line{'s' if staged.count != 1 else ''} would leave this Mac for {repo_id}; "
                           f"the yes must name that number (it named {confirmed_lines}).")
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi()
    me = api.whoami(token=token)
    if repo_id.split("/", 1)[0] != me.get("name"):
        raise NotYourNamespace(f"{repo_id} is not under this token's own account ({me.get('name')}/...): "
                               "the dataset must be the person's own")
    if "repo.write" in _lacks(me):
        raise HuggingFaceTokenRejected("this Hugging Face token may not write to your repositories (repo.write missing); "
                                       "give it write access on huggingface.co, or save one that has it in Settings.")
    try:
        existing = api.dataset_info(repo_id, token=token)
    except Exception as exc:  # noqa: BLE001 -- only "not found" is fine: the dataset is then created below
        if getattr(getattr(exc, "response", None), "status_code", None) != 404 and type(exc).__name__ != "RepositoryNotFoundError":
            raise
        existing = None
    if existing is not None and existing.private is not True:
        raise PublicDatasetRefused(f"{repo_id} exists and is public: training data goes only to a private dataset")
    api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True, token=token)
    if api.dataset_info(repo_id, token=token).private is not True:
        raise PublicDatasetRefused(f"{repo_id} is not private after it was created: nothing was uploaded")
    # Only the files stage_dataset wrote, by name: whatever else sits in the folder does not leave (review 509).
    api.upload_folder(folder_path=str(staged.path), repo_id=repo_id, repo_type="dataset", token=token,
                      allow_patterns=list(staged.files))
    return Pushed(repo_id, staged.count)
