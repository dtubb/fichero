"""The project's rule for a model call that leaves this Mac (`ai.where.one-egress-gate`, #5368).

One question, asked where every model call is built (`llm.get_langchain_model`) and at the calls that do not build a
model (`llm._enforce_local_only_provider`): may the pages of the project this call belongs to go to this place? The
project is the library the call runs under (`observability.episodes._episode_library_path`: set by the API for each
request that names a library, by the workflow executor and by every stored job). Its rule is Set Up's `cloud_allowed`
answer; a project that has not said yes keeps its pages on this Mac. A call under NO library fails closed too: no
exemption is built, because none is needed today (the chat requires a library; provider key tests and model lists do not
meet the gate at all, since they send a key or ask for a list, never content, and the sweep test pins that).
"""

from __future__ import annotations

from pathlib import Path

_CACHE: dict[str, tuple[tuple[int, int], bool | None]] = {}  # setup.yaml path -> (mtime, the project's own answer, None when it has not given one): the file is read when it changes


def project_allows_leaving(library: str | None) -> bool:
    """Whether the project at `library` has said that its pages may go to a cloud model. A project that has not answered for
    itself (no setup saved, or no `cloud_allowed` in it) starts from the app's own yes to the cloud
    (`recipes.places.inherits_cloud`); an answer that is not a yes, or a file that cannot be read, is no: a refusal never
    depends on a file being well formed. With no library the answer is no."""
    if not library:
        return False
    from fichero_server.recipes.places import project_says_cloud
    from fichero_server.recipes.project import FOLDER

    path = Path(library) / FOLDER / "setup.yaml"
    try:
        st = path.stat()
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return project_says_cloud(None)  # no setup saved: a new project, from the app's setting
    key = str(path)
    hit = _CACHE.get(key)
    if hit and hit[0] == mtime:
        return project_says_cloud(hit[1])
    try:
        import yaml

        answers = yaml.safe_load(path.read_text(encoding="utf-8"))
        said = answers.get("cloud_allowed") if isinstance(answers, dict) else False
        allowed = said if isinstance(said, bool) or said is None else False  # anything but yes, no or absent is no
    except Exception:  # noqa: BLE001 -- unreadable means not a yes
        allowed = False
    _CACHE[key] = (mtime, allowed)
    return project_says_cloud(allowed)


def current_library() -> str | None:
    """The project the call is for: the one the run or chat bound (`recipes.places.bound_library`; a Set Up try's scratch copy
    maps to its REAL project there), else the one the request or stored job runs under. The only place the gate reads it."""
    from fichero_server.observability.episodes import _episode_library_path
    from fichero_server.recipes.places import bound_library

    bound = bound_library()
    return str(bound) if bound is not None else _episode_library_path.get()


def project_name(library: str | None) -> str | None:
    return Path(library).stem if library else None


def require_project_yes(library: str | None, where: str) -> None:
    """For a package that is SENT (training, a read at scale): the person's per-request yes is not enough; the project's own
    rule must say yes too (`ai.where.batch-sends-ask-the-project`, #5368). Raises ValueError, in words."""
    if not project_allows_leaving(library):
        raise ValueError(f"{where} would send pages of the project {project_name(library) or '(none open)'}, which keeps "
                         "its pages on this Mac. Allow cloud models for it in Set Up first.")
