"""The bake-off's winning reads become training lines in a PRIVATE Hugging Face dataset (#5894;
`compute.tune.bakeoff-reads-become-training-lines`, `compute.tune.training-data-goes-only-to-a-private-dataset`).

RED until `training/bakeoff_lines.py` exists. `HfApi` is replaced at the boundary: no network, no token, no upload.
The pages are tiny drawn images; nothing here is the owner's data.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from fichero_server.training import bakeoff_lines as bl
from fichero_server.training.hf_jobs import HuggingFaceTokenRejected, NoHuggingFaceToken


def _lines_json(tmp_path: Path) -> Path:
    """What the harness writes: four lines of one page, three readers (kraken, vision, mlx:m)."""
    poly = lambda y: [[10, y], [390, y], [390, y + 30], [10, y + 30]]  # noqa: E731
    rows = [
        {"page": "p0.png", "id": "0", "polygon": poly(10), "kraken": "hola", "vision": "hola", "mlx:m": "hola",
         "agreement": "agree"},
        {"page": "p0.png", "id": "1", "polygon": poly(50), "kraken": "mundo", "vision": "mvndo", "mlx:m": "mundo",
         "agreement": "split"},
        {"page": "p0.png", "id": "2", "polygon": poly(90), "kraken": "", "vision": "", "mlx:m": "adios",
         "agreement": None},
        {"page": "p0.png", "id": "3", "polygon": poly(130), "kraken": "x", "vision": "x", "mlx:m": "",
         "agreement": "agree"},
    ]
    path = tmp_path / "lines.json"
    path.write_text(json.dumps({"label": "model reference (mlx:m), not ground truth", "arms": ["kraken", "vision", "mlx:m"],
                                      "lines": rows}))
    return path


def _pages(tmp_path: Path) -> Path:
    folder = tmp_path / "pages"
    folder.mkdir()
    im = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(im).text((10, 10), "page", fill="black")
    im.save(folder / "p0.png")
    return folder


def test_a_winners_text_is_kept_only_where_every_reader_that_answered_agrees(tmp_path):
    got = bl.winning_lines(_lines_json(tmp_path), winner="mlx:m")
    assert [(g.line_id, g.text) for g in got.lines] == [("0", "hola")], "split, unread and the winner's empty line are out"
    assert got.left_out == {"split": 1, "fewer_than_two_readers": 1, "empty": 1}
    line = got.lines[0]
    assert line.read_by == "mlx:m" and line.checked_by_person is False and line.agreed_by == ["kraken", "vision", "mlx:m"]


def test_a_winner_that_is_not_in_the_file_is_refused_in_words(tmp_path):
    with pytest.raises(ValueError, match="not an arm in .*lines.json.*kraken.*vision.*mlx:m"):
        bl.winning_lines(_lines_json(tmp_path), winner="gemini")


def test_staging_writes_each_line_picture_and_a_pairs_file_and_counts_them(tmp_path):
    got = bl.winning_lines(_lines_json(tmp_path), winner="mlx:m")
    out = tmp_path / "stage"
    staged = bl.stage_dataset(got, _pages(tmp_path), out)
    assert staged.count == 1
    [row] = [json.loads(x) for x in (out / "pairs.jsonl").read_text().splitlines()]
    assert row["text"] == "hola" and row["read_by"] == "mlx:m" and row["checked_by_person"] is False
    assert (out / row["image"]).exists() and Image.open(out / row["image"]).height > 0


def test_staging_refuses_a_folder_inside_any_git_work_tree_not_only_this_checkout(tmp_path):
    repo = Path(bl.__file__).resolve().parents[4]  # .../fichero-server/src/fichero_server/training -> the checkout
    other = tmp_path / "someone-elses-clone"
    (other / ".git").mkdir(parents=True)
    got = bl.winning_lines(_lines_json(tmp_path), winner="mlx:m")
    for inside in (repo / "scratch-stage", other / "data" / "stage"):
        with pytest.raises(ValueError, match="inside the git work tree"):
            bl.stage_dataset(got, _pages(tmp_path) if not (tmp_path / "pages").exists() else tmp_path / "pages", inside)
        assert not inside.exists()


def test_the_dataset_card_says_these_are_a_models_readings_not_a_persons_check(tmp_path):
    staged = _staged(tmp_path)
    card = (staged.path / "README.md").read_text()
    assert "not checked by a person" in card and "not ground truth" in card and "mlx:m" in card and "private" in card


class Api:
    """The Hub at the boundary: records every call, uploads nothing."""

    def __init__(self, *, role="write", existing_private: bool | None = None, created_private=True):
        self.calls: list[tuple[str, dict]] = []
        self.role, self.existing_private, self.created_private = role, existing_private, created_private

    def whoami(self, **kw):
        self.calls.append(("whoami", kw))
        return {"name": "historian", "auth": {"accessToken": {"role": self.role}}}

    def create_repo(self, repo_id, **kw):
        self.calls.append(("create_repo", {"repo_id": repo_id, **kw}))

    def dataset_info(self, repo_id, **kw):
        self.calls.append(("dataset_info", {"repo_id": repo_id}))
        private = self.existing_private if self.existing_private is not None and not any(
            c[0] == "create_repo" for c in self.calls) else self.created_private
        return SimpleNamespace(private=private)

    def upload_folder(self, **kw):
        self.calls.append(("upload_folder", kw))

    def names(self):
        return [c[0] for c in self.calls]


def _staged(tmp_path):
    return bl.stage_dataset(bl.winning_lines(_lines_json(tmp_path), winner="mlx:m"), _pages(tmp_path), tmp_path / "stage")


def test_a_push_creates_a_private_dataset_checks_it_is_private_then_uploads(tmp_path):
    api = Api()
    result = bl.push_private_dataset(_staged(tmp_path), "historian/test2-lines", token="hf_x", api=api, confirmed_lines=1)
    assert api.names() == ["whoami", "dataset_info", "create_repo", "dataset_info", "upload_folder"], \
        "who the token is, is it already public, create private, is it private, and only then upload"
    create = next(kw for name, kw in api.calls if name == "create_repo")
    assert create["private"] is True and create["repo_type"] == "dataset" and create["token"] == "hf_x"
    upload = next(kw for name, kw in api.calls if name == "upload_folder")
    assert upload["repo_type"] == "dataset" and upload["repo_id"] == "historian/test2-lines"
    assert result.repo_id == "historian/test2-lines" and result.lines == 1


def test_there_is_no_way_to_ask_for_a_public_dataset():
    import inspect

    params = inspect.signature(bl.push_private_dataset).parameters
    assert not any("public" in name or name == "private" for name in params)


def test_no_token_or_no_confirmation_is_refused_before_the_hub_is_touched(tmp_path):
    staged = _staged(tmp_path)
    for kw, error, words in ((dict(token="", confirmed_lines=1), NoHuggingFaceToken, "Hugging Face token"),
                             (dict(token="hf_x", confirmed_lines=None), bl.NotConfirmed, "1 line"),
                             (dict(token="hf_x", confirmed_lines=7), bl.NotConfirmed, "1 line")):
        api = Api()
        with pytest.raises(error, match=words):
            bl.push_private_dataset(staged, "historian/test2-lines", api=api, **kw)
        assert api.names() == [], "the fake Hub saw no call at all"


def test_a_token_that_may_not_write_or_a_public_dataset_is_refused_before_anything_is_created(tmp_path):
    staged = _staged(tmp_path)
    for api, error, words in ((Api(role="read"), HuggingFaceTokenRejected, "write"),
                              (Api(existing_private=False), bl.PublicDatasetRefused, "public")):
        with pytest.raises(error, match=words):
            bl.push_private_dataset(staged, "historian/test2-lines", token="hf_x", api=api, confirmed_lines=1)
        assert "create_repo" not in api.names() and "upload_folder" not in api.names()


def test_a_dataset_that_comes_back_public_is_refused_and_nothing_is_uploaded(tmp_path):
    api = Api(created_private=False)
    with pytest.raises(bl.PublicDatasetRefused, match="not private"):
        bl.push_private_dataset(_staged(tmp_path), "historian/test2-lines", token="hf_x", api=api, confirmed_lines=1)
    assert "upload_folder" not in api.names()


def test_a_dataset_under_another_account_is_refused_before_anything_is_created(tmp_path):
    api = Api()
    with pytest.raises(bl.NotYourNamespace, match="own account"):
        bl.push_private_dataset(_staged(tmp_path), "someone-else/lines", token="hf_x", api=api, confirmed_lines=1)
    assert api.names() == ["whoami"]


def test_staging_refuses_a_folder_that_already_holds_something(tmp_path):
    got = bl.winning_lines(_lines_json(tmp_path), winner="mlx:m")
    full = tmp_path / "desktop"
    full.mkdir()
    (full / "passport.pdf").write_text("not ours")
    with pytest.raises(ValueError, match="not empty"):
        bl.stage_dataset(got, _pages(tmp_path), full)
    assert [p.name for p in full.iterdir()] == ["passport.pdf"], "nothing was written into it"


def test_only_the_files_that_were_staged_are_uploaded_by_name(tmp_path):
    staged = _staged(tmp_path)
    (staged.path / "stray-note.txt").write_text("added after staging")
    api = Api()
    bl.push_private_dataset(staged, "historian/test2-lines", token="hf_x", api=api, confirmed_lines=1)
    upload = next(kw for name, kw in api.calls if name == "upload_folder")
    assert sorted(upload["allow_patterns"]) == sorted(staged.files)
    assert "README.md" in staged.files and "pairs.jsonl" in staged.files and any(f.startswith("lines/") for f in staged.files)
    assert "stray-note.txt" not in upload["allow_patterns"]


def test_crops_are_named_by_number_so_a_page_name_with_glob_characters_still_uploads(tmp_path):
    import shutil

    lines = _lines_json(tmp_path)
    data = json.loads(lines.read_text())
    for row in data["lines"]:
        row["page"] = "p[0]*?.png"
    lines.write_text(json.dumps(data))
    pages = _pages(tmp_path)
    shutil.move(str(pages / "p0.png"), str(pages / "p[0]*?.png"))
    staged = bl.stage_dataset(bl.winning_lines(lines, winner="mlx:m"), pages, tmp_path / "stage")
    assert "lines/00001.jpg" in staged.files and (staged.path / "lines" / "00001.jpg").exists()
    import fnmatch

    assert all(any(fnmatch.fnmatchcase(f, pattern) for pattern in staged.files) for f in staged.files), \
        "every staged file matches its own allow_pattern"
