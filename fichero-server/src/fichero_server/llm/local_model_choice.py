"""Which local model this Mac can run, and which AI defaults it gets (#5520, #5496).

ONE function answers "can this Mac run this local model for this use": `runs_here`. It reads the
same two facts everywhere: the catalogue's memory requirement for the model (`mlx_model_store`'s
`min_memory_bytes`, or `page_memory_bytes` when reading a page needs more) and this Mac's unified
memory (`get_local_inference_capabilities`). The AI defaults, Settings' local model, the local
model server's switch and the Start plan all ask it, so none of them can choose a model whose own
card says it cannot run here.

The defaults never name a provider this build lacks: Apple Intelligence needs the fm-bridge binary,
and an engine without it falls back to this Mac's local model server, saying which and why.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

#: Names a request uses for "whatever the local model server serves by default".
DEFAULT_LOCAL_MODEL_NAMES = frozenset({"", "default", "local-model"})
#: The app setting that holds Settings › AI's local model (ai-defaults `local_model`).
LOCAL_MODEL_SETTING_KEY = "default_local_model"
#: Where the person changes it, named in every message that tells them to.
LOCAL_MODEL_SETTING_NAME = "Settings › AI › Defaults › Local model"
#: The dev-only override of the server's default model (never read by the app's own UI).
DEV_MODEL_ENV = "FICHERO_OMLX_MODEL"
#: The app setting that records why each default was chosen, as JSON {setting key: why}.
CHOSEN_BECAUSE_SETTING_KEY = "default_chosen_because"

_TEXT_TIER_KEYS = ("text", "small", "medium", "large")


def _gb(n: int) -> str:
    return f"{max(1, round(n / 1024**3))} GB"


def _store() -> Any:
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    return get_mlx_model_store()


def _catalog() -> Iterable[Any]:
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

    return MANAGED_MLX_MODELS.values()


def runs_here(spec: Any, capability: str = "text", *, capabilities: Any = None) -> tuple[bool, str | None]:
    """Whether this Mac can run `spec` for `capability` ("vision" reads a page, "text" does not),
    and if not, why in words: the model's own memory requirement against this Mac's memory."""
    from fichero_server.llm.local_inference import check_local_model_hardware, get_local_inference_capabilities

    current = capabilities or get_local_inference_capabilities()
    ok, why = check_local_model_hardware(
        display_name=spec.display_name, min_memory_bytes=spec.min_memory_bytes, capabilities=current)
    if not ok:
        return False, why
    page = getattr(spec, "page_memory_bytes", None)
    if capability == "vision" and page and current.physical_memory_bytes and current.physical_memory_bytes < page:
        return False, (f"{spec.display_name} needs {_gb(page)} of unified memory to read a page; "
                       f"this Mac has {_gb(current.physical_memory_bytes)}")
    return True, None


@dataclass(frozen=True)
class LocalModelChoice:
    """The local model chosen for one use, or None, and why in words."""

    model_id: str | None
    reason: str


def choose_local_model(capability: str, *, store: Any = None, catalog: Iterable[Any] | None = None,
                       capabilities: Any = None) -> LocalModelChoice:
    """The best catalogue model with `capability` that runs here: an installed one first, then a
    verified one, then the larger (the more capable). Never one `runs_here` refuses."""
    store = store or _store()
    candidates = [s for s in (catalog if catalog is not None else _catalog()) if capability in s.capabilities]
    runnable, refused = [], []
    for spec in candidates:
        ok, why = runs_here(spec, capability, capabilities=capabilities)
        (runnable if ok else refused).append((spec, why))
    if not runnable:
        return LocalModelChoice(None, f"no {capability} model in the local catalogue runs on this Mac"
                                + (f" ({refused[0][1]})" if refused else ""))
    ranked = sorted((spec for spec, _ in runnable), key=lambda s: (
        not store.is_complete(s), s.tested_status != "verified", -s.download_size_bytes, s.model_id))
    best = ranked[0]
    installed = store.is_complete(best)
    why = (f"{best.display_name} is {'installed and is' if installed else 'not installed yet; it is'} the "
           f"{'verified ' if best.tested_status == 'verified' else ''}{capability} model this Mac runs best")
    if refused:
        why += f" ({refused[0][1]})"
    if not installed:
        why += "; install it in Settings › AI to use it"
    return LocalModelChoice(best.model_id, why)


def _text_model_beside_the_reader() -> LocalModelChoice:
    """The text default on the local server: the vision model chosen for this Mac when it is
    installed (it also does text, and one server holds one model: a page read and its names found
    then never swap models), else the best text model this Mac runs."""
    reader = choose_local_model("vision")
    store = _store()
    if reader.model_id is not None and store.is_complete(store.spec(reader.model_id)):
        return LocalModelChoice(reader.model_id, f"{reader.reason}; it also does text, so one model stays loaded")
    return choose_local_model("text")


def apple_intelligence_in_this_build() -> bool:
    """Whether this engine can run Apple Intelligence: the fm-bridge binary is present and the
    device can run it (the same facts the Apple chat path refuses on)."""
    from fichero_server.llm import _find_fm_bridge_binary, _fm_bridge_unavailable_reason

    return _fm_bridge_unavailable_reason() is None and _find_fm_bridge_binary() is not None


def machine_ai_defaults(*, apple_intelligence: bool | None = None,
                        local_text: LocalModelChoice | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """The AI defaults for THIS Mac and THIS build, and why, as ({setting key: value}, {setting key: why}).

    The factory baseline is on-device Apple. A text tier names Apple Intelligence only when this
    build carries it; otherwise it falls to the local model server's best text model for this Mac.
    Apple Vision and Apple Speech are system frameworks, not the fm-bridge, so they stay."""
    from fichero_server.db.app import FACTORY_AI_DEFAULTS

    values, because = dict(FACTORY_AI_DEFAULTS), {}
    if apple_intelligence is None:
        apple_intelligence = apple_intelligence_in_this_build()
    if apple_intelligence:
        for tier in _TEXT_TIER_KEYS:
            because[f"default_{tier}_provider"] = "Apple Intelligence is in this build and runs on this Mac"
        return values, because
    local_text = local_text or _text_model_beside_the_reader()
    if local_text.model_id is None:
        for tier in _TEXT_TIER_KEYS:
            because[f"default_{tier}_provider"] = (
                f"Apple Intelligence is not in this build, and {local_text.reason}: add a cloud provider "
                "in Settings › AI")
        return values, because
    for tier in _TEXT_TIER_KEYS:
        values[f"default_{tier}_provider"] = "omlx"
        values[f"default_{tier}_model"] = local_text.model_id
        because[f"default_{tier}_provider"] = (
            f"Apple Intelligence is not in this build, so text runs on this Mac's local model server: "
            f"{local_text.reason}")
    return values, because


def record_chosen_because(app_db: Any, because: dict[str, str]) -> None:
    """Keep why each default was chosen, for Settings to say (ai-defaults `chosen_because`)."""
    app_db.set_setting(CHOSEN_BECAUSE_SETTING_KEY, json.dumps(because, sort_keys=True))


def read_chosen_because(app_db: Any) -> dict[str, str]:
    raw = app_db.get_setting(CHOSEN_BECAUSE_SETTING_KEY)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{CHOSEN_BECAUSE_SETTING_KEY} is not JSON: {raw[:80]!r}") from exc
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def default_local_model() -> LocalModelChoice:
    """The model the app-managed local server loads when a request names none: the dev override,
    else Settings' local model, else the vision model chosen for this Mac."""
    import os

    env = os.environ.get(DEV_MODEL_ENV)
    if env:
        return LocalModelChoice(env, f"the developer override {DEV_MODEL_ENV} names it")
    from fichero_server.db.app import get_app_db

    chosen = get_app_db().get_setting(LOCAL_MODEL_SETTING_KEY)
    if chosen:
        return LocalModelChoice(chosen, f"chosen in {LOCAL_MODEL_SETTING_NAME}")
    pick = choose_local_model("vision")
    if pick.model_id is None:
        # Nothing in the catalogue runs here: the smallest model is still the honest name to
        # serve, and starting it is refused with the true reason (runs_here / the store).
        smallest = min(_catalog(), key=lambda s: s.download_size_bytes)
        return LocalModelChoice(smallest.model_id, pick.reason)
    return pick


class LocalModelRefused(RuntimeError):
    """A local model this Mac cannot serve for a step, said with the reason and the fix."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        #: "unknown", "not-installed" or "cannot-run".
        self.kind = kind


def _installed_alternatives(capability: str, store: Any, exclude: str | None) -> list[str]:
    out = []
    for spec in _catalog():
        if spec.model_id == exclude or capability not in spec.capabilities or not store.is_complete(spec):
            continue
        if runs_here(spec, capability)[0]:
            out.append(spec.display_name)
    return out


def local_model_problem(name: str | None, capability: str = "text", *, store: Any = None) -> LocalModelRefused | None:
    """Why this Mac's local model server cannot serve `name` for `capability`, or None if it can.

    The same answer before Start (the plan) and before the server switches (a run): a model not in
    the catalogue, not installed, or whose own card says it cannot run on this Mac's memory."""
    store = store or _store()
    model_id = store.canonical_id(name)
    if model_id is None:
        others = _installed_alternatives(capability, store, None)
        return LocalModelRefused(
            f"{name} is not a model this Mac's local model server can run: it is not in Fichero's local "
            f"model catalogue. " + (f"Choose an installed one: {', '.join(others)}." if others
                                    else "Install one in Settings › AI."), kind="unknown")
    spec = store.spec(model_id)
    ok, why = runs_here(spec, capability)
    if not ok:
        fit = choose_local_model(capability, store=store)
        fix = f" Choose {store.spec(fit.model_id).display_name} instead." if fit.model_id else ""
        return LocalModelRefused(f"{why}.{fix}", kind="cannot-run")
    if not store.is_complete(spec):
        others = _installed_alternatives(capability, store, model_id)
        fix = f", or choose an installed one: {', '.join(others)}" if others else ""
        return LocalModelRefused(
            f"{spec.display_name} is not installed on this Mac. Install it in Settings › AI › Local models"
            f"{fix}.", kind="not-installed")
    return None


def model_to_serve(requested: str | None, *, store: Any = None) -> str:
    """The store id the local server must serve for a request: the one it names, or the default
    when it names none. A name the catalogue does not know is returned as given (the caller refuses
    it, or a developer's custom server command takes it)."""
    store = store or _store()
    name = (requested or "").strip().removeprefix("omlx/")
    if name in DEFAULT_LOCAL_MODEL_NAMES:
        return default_local_model().model_id or ""
    return store.canonical_id(name) or name
