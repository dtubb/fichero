"""The project's rule for a model call that leaves this Mac (`ai.where.one-egress-gate`, #5368).

One question, asked where every model call is built (`llm.get_langchain_model`) and at the calls that do not build a
model (`llm._enforce_local_only_provider`): may the pages of the project this call belongs to go to this place? The
project is the library the call runs under (`observability.episodes._episode_library_path`: set by the API for each
request that names a library, by the workflow executor and by jobs). Its rule is Set Up's `cloud_allowed` answer; a
project that has not said yes keeps its pages on this Mac. A call under no library has no project to ask; only the
engine-wide switch (`llm.is_local_only`) applies to it.
"""

from __future__ import annotations

from pathlib import Path

_CACHE: dict[str, tuple[float, bool]] = {}  # setup.yaml path -> (mtime, allowed): the file is read when it changes


def project_allows_leaving(library: str | None) -> bool:
    """Whether the project at `library` has said that its pages may go to a cloud model. True when there is no library
    (nothing to ask); False when the project has not said yes (no setup saved, an unreadable file, an answer that is not
    a yes): a refusal never depends on a file being well formed."""
    if not library:
        return True
    from fichero_server.recipes.project import FOLDER

    path = Path(library) / FOLDER / "setup.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    key = str(path)
    hit = _CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        import yaml

        answers = yaml.safe_load(path.read_text(encoding="utf-8"))
        allowed = isinstance(answers, dict) and answers.get("cloud_allowed") is True
    except Exception:  # noqa: BLE001 -- unreadable means not a yes
        allowed = False
    _CACHE[key] = (mtime, allowed)
    return allowed


def current_library() -> str | None:
    from fichero_server.observability.episodes import _episode_library_path

    return _episode_library_path.get()
