"""The engine's one mapping from a failure to what a person is told (`run.fail.kinds-table`, #6354).

`classify` is the table in `specs/compute/runner-reliability.md`: the exception's TYPE decides first, its status code or words only
when it has no type of its own, and what the table does not name is `unexpected` (a bug in Fichero), never silence.
`RunFailure` is the served model; `redact` is the one function that takes what is private out of any text a report may carry.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional, get_args

from pydantic import BaseModel, Field

from fichero_server.llm.refusal import CloudRefusal

Kind = Literal["no-credit", "key-refused", "rate-limited", "cap-refused", "images-refused", "model-error", "model-missing",
               "runtime-unavailable", "memory", "network", "files-unavailable", "model-broken", "library-closed",
               "export-folder-gone", "interrupted", "unexpected"]
KINDS: tuple[str, ...] = get_args(Kind)
#: The kinds that PAUSE the run instead of failing it (`runner.kinds.pause-or-fail-is-the-tables`, #6675, runner-reliability section 1):
#: the cause is outside the work and Continue carries on once it is put right. Every other kind fails the item and goes on.
PAUSES = frozenset({"no-credit", "key-refused", "rate-limited", "cap-refused", "images-refused", "network", "memory",
                    "library-closed", "export-folder-gone"})
#: The kinds the engine retries by itself, bounded, before it pauses or fails (the table's "engine retries first" column).
ENGINE_RETRIES = frozenset({"rate-limited", "network", "memory", "model-error", "interrupted"})
ActionKind = Literal["retry", "resume", "open-settings", "choose-model", "report-bug", "reconnect", "raise-to", "allow-everywhere",
                     "allow-project", "allow-once", "over-cap-once", "choose-folder"]

PROVIDERS_CONTROL = "settings.ai.providers"
LOCAL_MODELS_CONTROL = "settings.ai.localModels"


class ModelBrokenError(Exception):
    """A model that is on this Mac but will not load (`model-broken`): `model` is its display name; the message is for the log."""

    def __init__(self, model: str, message: str = "") -> None:
        super().__init__(message or f"{model} could not be loaded")
        self.model = model


class FailureAction(BaseModel):
    kind: ActionKind
    control: Optional[str] = Field(default=None, description="`open-settings`: the control's id; `choose-folder`: the kept "
                                                             "export's id")
    usd: Optional[float] = Field(default=None, description="a refusal's `raise-to`: the cap that lets the run through")
    retry_after_seconds: Optional[float] = Field(default=None, description="`retry`: how long the provider asked to wait")


class RunFailure(BaseModel):
    """Why a run did not finish, what to do, and the buttons for it. One shape for the row, the status route, the jobs list,
    the stream and the bug report."""

    kind: Kind
    words: str = Field(description="what happened, naming the provider and model by display name")
    fix: str = Field(description="what to do about it")
    actions: list[FailureAction] = Field(default_factory=list, description="the buttons, in the order to offer them")
    provider: Optional[str] = None
    model: Optional[str] = None
    step: Optional[str] = None
    pages_done: Optional[int] = None
    pages_total: Optional[int] = None
    row_words: str = Field(default="", description="the table row's words: at most eight, never a sentence cut short")
    exception_type: Optional[str] = Field(default=None, description="the exception's class name; never its message")
    detail: str = Field(default="", description="the error's first line, redacted")
    refusal: Optional[CloudRefusal] = Field(default=None, description="`cap-refused` and `images-refused`: the typed refusal")
    pauses: bool = Field(default=False, description="the kind's rule: the run PAUSES for it and Continue goes on (else it fails the item)")
    engine_retries: bool = Field(default=False, description="the engine retries this kind by itself, bounded, before pausing or failing")


# --- redaction -------------------------------------------------------------------------------------------------------------

_HOME = re.compile(r"/(?:Users|home)/[^/\s'\"]+")
_PATH = re.compile(r"(?<![\w:])(?:~|<path>)?(?:/[^/\s'\"<>()\[\],;]+){2,}/?")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}")
_KEY_SHAPE = re.compile(r"\b(?:sk|pk|rk|hf|gsk|xox[abp]|ghp|AIza)[-_A-Za-z0-9]{12,}")
_SECRET_WORD = re.compile(r"(?i)\b(api[_-]?key|key|token|secret|password|passwd|authorization)(\s*[:=]\s*|\s+)[^\s,;&'\"]{4,}")
_ID_VALUE = re.compile(r"(?i)\b(document[_-]?id|doc[_-]?id|page[_-]?id)(\s*[:=]\s*)[^\s,;&'\"]+")
_LONG_QUOTED = re.compile(r"(['\"])[^'\"\n]{40,}\1")  # a long quoted string in an error is a page's text or a model's answer
_URL_SECRET = re.compile(r"(?i)([?&](?:api[_-]?key|key|token|access_token|secret|sig|signature)=)[^&\s'\"]+")


def redact(text: str) -> str:
    """Text with what is private taken out: the home folder becomes `~`, every other `/…/` path `<path>`, a bearer header, a key
    shape, a `key=`/`token:` value and a document or page id `<redacted>`, and a long quoted string (a page's text or a model's
    answer carried in an error message) `<text>`. Order matters: the home folder is named before paths are generalised."""
    if not text:
        return ""
    out = _HOME.sub("~", text)
    out = _PATH.sub("<path>", out)
    out = _BEARER.sub(lambda m: f"{m.group(1)} <redacted>", out)
    out = _URL_SECRET.sub(lambda m: f"{m.group(1)}<redacted>", out)
    out = _SECRET_WORD.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", out)
    out = _ID_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", out)
    out = _LONG_QUOTED.sub(lambda m: f"{m.group(1)}<text>{m.group(1)}", out)
    return _KEY_SHAPE.sub("<redacted>", out)


# --- the table -------------------------------------------------------------------------------------------------------------

_ICLOUD = ("stored in icloud", "not downloaded locally", ".icloud", "is in icloud")
_MISSING_FILE = ("no such file", "file not found")
_NETWORK = ("dns", "connection", "timeout", "timed out", "network", "unreachable")


def _first_line(exc: BaseException | None, text: str) -> str:
    raw = text or (str(exc) if exc is not None else "")
    return redact(raw.strip().splitlines()[0][:300]) if raw.strip() else ""


def _of(exc: BaseException | None, *names: str) -> bool:
    """Whether the exception is an instance of a class called one of `names` (a class that cannot be imported on every
    build, such as the Kraken runtime's, is matched by name down its MRO)."""
    return exc is not None and any(c.__name__ in names for c in type(exc).__mro__)


def _status(exc: BaseException | None, text: str) -> int | None:
    from fichero_server.llm import _extract_exc_status_code

    if exc is not None:
        try:
            code = _extract_exc_status_code(exc)
        except Exception:  # noqa: BLE001 - classification must never crash
            code = None
        if code is not None:
            return code
    found = re.search(r"\b(40[0-9]|42[0-9]|5\d\d)\b", text or (str(exc) if exc is not None else ""))
    return int(found.group(1)) if found else None


def _library_closed(exc: BaseException | None, text: str) -> bool:
    """A job's project was closed under it: DuckDB's own words for a connection that is gone."""
    low = (text or (str(exc) if exc is not None else "")).lower()
    return "connection already closed" in low or ("the library" in low and "was closed" in low)


def _provider_kind(exc: BaseException | None, text: str, status: int | None) -> str | None:
    """The kind for a provider that cannot answer, from its typed errors first, then its status and words."""
    from fichero_server.llm import ProviderQuotaError
    from fichero_server.workflows import circuit_breaker as cb

    if isinstance(exc, cb.ProviderKeyRefusedError):
        return "key-refused"
    if isinstance(exc, cb.ProviderQuotaExhaustedError):
        return "no-credit"
    if isinstance(exc, cb.ProviderRateLimitedError):
        return "rate-limited"
    low = (text or (str(exc) if exc is not None else "")).lower()
    if exc is not None and (isinstance(exc, ProviderQuotaError) or status in (401, 402, 429)):
        try:
            fatal = cb.classify_provider_error(exc) == "fatal"
        except Exception:  # noqa: BLE001 -- a breaker that cannot classify falls through to the status below
            fatal = False
        if fatal:
            return "key-refused" if cb.fatal_cause(exc) == "key" else "no-credit"
        if status in (401, 402):  # the breaker's own words did not match, the status did
            return "key-refused" if status == 401 else "no-credit"
        return "rate-limited"
    if status == 402 or any(w in low for w in cb.NO_CREDIT_WORDS):
        return "no-credit"
    if status in (401, 403) or any(w in low for w in (*cb.KEY_REFUSED_WORDS, "unauthorized", "forbidden", "api key")):
        return "key-refused"
    if status == 429 or "rate limit" in low or "rate_limit" in low or "quota" in low:
        return "rate-limited"
    return None


def kind_of(exc: BaseException | None, text: str = "") -> tuple[str, CloudRefusal | None]:
    """The failure kind, and the typed refusal a refusal kind carries. The type of the exception decides first."""
    from fichero_server.execution.throttle import MemoryShortError
    from fichero_server.llm import (
        AppleUnavailableError, EgressRefusedError, LocalOnlyViolationError, StructuredCallEmptyError, StructuredDecodeError,
    )
    from fichero_server.llm.local_inference import LocalModelMemoryUnavailableError, LocalModelNotInstalledError
    from fichero_server.llm.spend import CloudSpendRefusedError

    refusal = getattr(exc, "refusal", None)
    if isinstance(exc, CloudSpendRefusedError):
        return "cap-refused", refusal
    if isinstance(exc, (EgressRefusedError, LocalOnlyViolationError)):
        return "images-refused", refusal
    if isinstance(exc, (MemoryShortError, LocalModelMemoryUnavailableError)):
        return "memory", None
    if isinstance(exc, LocalModelNotInstalledError):
        return "model-missing", None
    if isinstance(exc, ModelBrokenError) or _of(exc, "EmbedderUnavailable"):
        return "model-broken", None
    if _of(exc, "ExportFolderGone"):
        return "export-folder-gone", None
    if _library_closed(exc, text):
        return "library-closed", None
    if isinstance(exc, (StructuredDecodeError, StructuredCallEmptyError)):
        return "model-error", None  # before the runtime-missing types: a decode error is an AppleUnavailableError subclass
    if isinstance(exc, AppleUnavailableError) or _of(exc, "LocalInferenceRuntimeMissingError", "KrakenRuntimeMissingError"):
        return "runtime-unavailable", None
    status = _status(exc, text)
    kind = _provider_kind(exc, text, status)
    if kind:
        return kind, None
    low = (text or (str(exc) if exc is not None else "")).lower()
    if any(w in low for w in _ICLOUD) or any(w in low for w in _MISSING_FILE):
        return "files-unavailable", None
    if status == 404 or any(w in low for w in ("model_not_found", "model not found", "unknown model")):
        return "model-error", None
    if (status is not None and status >= 500) or "internal server error" in low or any(w in low for w in _NETWORK):
        return "network", None
    return "unexpected", None


def classify(exc: BaseException | None, text: str = "", *, step: str | None = None, provider: str | None = None,
             model: str | None = None, done: int | None = None, total: int | None = None) -> RunFailure:
    """The table: a failure and where the run was, as the words, the fix and the buttons a client shows."""
    kind, refusal = kind_of(exc, text)
    return _build(kind, refusal, exc, text, step=step, provider=provider, model=model, done=done, total=total)


def paused_reason(kind: str, provider: str | None = None) -> str:
    """The words of a job row paused for `kind` ("Paused: Out of credit at OpenRouter"); `kind_of_paused_reason` reads them back."""
    from fichero_server.workflows.circuit_breaker import provider_display

    return "Paused: " + row_words(kind, name=provider_display(provider) if provider else "the provider")


def kind_of_paused_reason(reason: str | None) -> str | None:
    """The pausing kind a job row's paused `reason` says (`paused_reason`), else None."""
    if not reason or not reason.startswith("Paused: "):
        return None
    said = reason[len("Paused: "):]
    for kind in sorted(PAUSES):
        template = _ROW_WORDS[kind]
        if re.fullmatch(re.escape(template).replace(re.escape("{name}"), ".+").replace(re.escape("{model}"), ".+"), said):
            return kind
    return None


def kind_of_failed_reason(reason: str | None) -> str | None:
    """The kind whose row words a failed job row's `reason` is (`jobs.failed_reason` writes them), else None for a reason that
    keeps its own words."""
    if not reason:
        return None
    for kind in KINDS:
        template = _ROW_WORDS[kind]
        if re.fullmatch(re.escape(template).replace(re.escape("{name}"), ".+").replace(re.escape("{model}"), ".+"), reason):
            return kind
    return None


def of_kind(kind: str, *, folder_for: str | None = None) -> RunFailure:
    """A kind's failure with no exception at hand: a job row the engine PAUSED for a cause a person removes (`jobs`
    `_PAUSED_NOT_FAILED`), listed with its fix. `folder_for`: the kept export a `choose-folder` action is for (#6588)."""
    built = _build(kind, None, None, "")
    if folder_for:
        built.actions = [a.model_copy(update={"control": folder_for}) if a.kind == "choose-folder" else a for a in built.actions]
    return built


def from_refusal(refusal: CloudRefusal | dict, **where: Any) -> RunFailure:
    """The failure of a run PAUSED at a cap or by the images rule: the kept typed refusal, as `classify` would carry it on the
    exception (`step`, `provider`, `model`, `done`, `total` as for `classify`)."""
    refusal = refusal if isinstance(refusal, CloudRefusal) else CloudRefusal.model_validate(refusal)
    return _build("images-refused" if refusal.kind == "images" else "cap-refused", refusal, None, "", **where)


#: The table row's words per kind (`run.fail.kinds-table`'s row-words column, the review 2026-11-13): at most eight tokens, the
#: provider or model by display name, never a sentence cut at a word boundary.
_ROW_WORDS: dict[str, str] = {
    "no-credit": "Out of credit at {name}",
    "key-refused": "{name} refused the key",
    "rate-limited": "{name} is limiting how fast you send",
    "cap-refused": "Paused at the spend cap",
    "images-refused": "Pages stay on this Mac",
    "model-error": "{model} could not do this step",
    "model-missing": "{model} is not downloaded",
    "runtime-unavailable": "No runtime for this step",
    "memory": "Not enough memory for {model}",
    "network": "Could not reach {name}",
    "files-unavailable": "Some pages' files could not be opened",
    "model-broken": "{model} could not be loaded",
    "library-closed": "Paused: the project closed",
    "export-folder-gone": "The export folder is gone",
    "interrupted": "Stopped before it finished",
    "unexpected": "Something went wrong in Fichero",
}


def row_words(kind: str, *, name: str = "the provider", model: str = "the model") -> str:
    """The ≤ 8-word line a table row shows for a failure kind; an unknown kind reads as `unexpected`."""
    return _ROW_WORDS.get(kind, _ROW_WORDS["unexpected"]).format(name=name, model=model)


def _build(kind: str, refusal: CloudRefusal | None, exc: BaseException | None, text: str, *, step: str | None = None, provider: str | None = None,
           model: str | None = None, done: int | None = None, total: int | None = None) -> RunFailure:
    from fichero_server.workflows.circuit_breaker import provider_display, retry_after_seconds

    prov = provider_display(provider or getattr(exc, "provider", "") or "") if (provider or getattr(exc, "provider", None)) else None
    name = prov or "the provider"
    mdl = model or getattr(exc, "model", None)
    shown_model = mdl or "The model"
    at = f"page {done} of {total}" if done is not None and total else None
    stopped = f", so the run stopped at {at}" if at else ", so the run stopped"
    kept = f" The {done} pages done are kept." if done else ""
    detail = _first_line(exc, text)
    words, fix, acts = _WORDS[kind](name=name, model=shown_model, stopped=stopped, kept=kept, detail=detail, step=step or "this step",
                                    kind_exc=type(exc).__name__ if exc is not None else "an error", done=done, total=total)
    if refusal is not None:
        words = refusal.words
        fix = "Use one of the buttons, then run it again." if kind in ("cap-refused", "images-refused") else fix
        acts = [FailureAction(kind=f.kind, control=f.control, usd=f.usd) for f in refusal.fixes] + [FailureAction(kind="resume")]
    if kind == "rate-limited":
        wait = retry_after_seconds(exc) if exc is not None else None
        acts = [a.model_copy(update={"retry_after_seconds": wait}) if a.kind == "retry" else a for a in acts]
    return RunFailure(kind=kind, words=words, fix=fix, actions=acts, provider=prov, model=mdl, step=step, pages_done=done,
                      pages_total=total, row_words=row_words(kind, name=name, model=shown_model),
                      exception_type=type(exc).__name__ if exc is not None else None, detail=detail, refusal=refusal,
                      pauses=kind in PAUSES, engine_retries=kind in ENGINE_RETRIES)


def credit_pause_failure(paused: dict, *, step: str | None = None, done: int | None = None,
                         total: int | None = None) -> RunFailure:
    """The failure a run PAUSED for credit carries (#6675, `recipes-run.credit.out-of-credit-pauses-and-asks`): the provider, out of
    credit or a credit limit, the provider's own words, and Continue first; the pause is not a failure of any page."""
    refused = paused.get("cause") == "key-refused"
    failure = _build("key-refused" if refused else "no-credit", None, None, paused.get("detail", ""), step=step,
                     provider=paused["provider"], done=done, total=total)
    name = failure.provider or "the provider"
    what = "refused the key" if refused else "has reached its credit limit" if paused.get("cause") == "credit-limit" else "is out of credit"
    failure.words = f"{name} {what}, so the run is paused. Nothing was lost."
    failure.fix = ("Check the key in Settings › AI › Providers, then Continue." if refused else
                   f"Add credit or raise the limit at {name}, then Continue; Fichero checks again and goes on from the first page not done.")
    failure.fix += " Fichero goes on from the first page not done." if refused else ""
    failure.actions = [_a("resume"), _a("open-settings", PROVIDERS_CONTROL)]
    return failure


def memory_pause_failure(paused: dict, *, step: str | None = None, done: int | None = None,
                         total: int | None = None) -> RunFailure:
    """The failure a run PAUSED for memory carries (`runner.memory.hold-not-kill`, #6075): a page was held for memory past its
    patience; the run is paused, not failed, and Continue goes on from the first page not done."""
    failure = _build("memory", None, None, paused.get("detail", ""), step=step, done=done, total=total)
    failure.words = "This Mac did not have the memory for this step, so the run is paused. Nothing was lost."
    failure.fix = ("Close other apps, or choose a smaller model, then Continue; "
                   "Fichero goes on from the first page not done.")
    failure.actions = [_a("resume"), _a("choose-model")]
    return failure


def _a(kind: str, control: str | None = None) -> FailureAction:
    return FailureAction(kind=kind, control=control)  # type: ignore[arg-type]


def _row(words: str, fix: str, *acts: FailureAction) -> tuple[str, str, list[FailureAction]]:
    return words, fix, list(acts)


_WORDS: dict[str, Any] = {
    "no-credit": lambda *, name, stopped, kept, **_: _row(
        f"{name} has no credit left, or this key's limit is reached{stopped}.{kept}",
        f"Add credit at {name}, or give Fichero a different key or provider, then run it again.",
        _a("open-settings", PROVIDERS_CONTROL), _a("choose-model"), _a("retry")),
    "key-refused": lambda *, name, stopped, **_: _row(
        f"{name} refused the key Fichero has for it{stopped}.",
        "Check the key in Settings › AI › Providers (paste it again, or make a new one), or switch this step to another provider.",
        _a("open-settings", PROVIDERS_CONTROL), _a("choose-model"), _a("retry")),
    "rate-limited": lambda *, name, stopped, **_: _row(
        f"{name} is limiting how fast Fichero can send{stopped}.",
        f"Wait a few minutes, then continue the run. A higher plan at {name}, or another provider, avoids it.",
        _a("resume"), _a("retry"), _a("choose-model")),
    "cap-refused": lambda **_: _row("A cloud spend cap stopped this run.", "Raise the cap, or run past it once.", _a("resume")),
    "images-refused": lambda **_: _row("This project keeps its pages on this Mac.",
                                       "Allow cloud models for the project, or choose a model on this Mac.", _a("resume")),
    "model-error": lambda *, name, model, detail, **_: _row(
        f"{model} at {name} could not do this step" + (f": {detail}." if detail else "."),
        "Choose another model for this step, then run it again.", _a("choose-model"), _a("retry")),
    "model-missing": lambda *, model, **_: _row(
        f"{model} is not downloaded to this Mac.", "Download it in Settings › AI › Local models, or choose another model.",
        _a("open-settings", LOCAL_MODELS_CONTROL), _a("choose-model")),
    "runtime-unavailable": lambda **_: _row("The runtime for this step is not available in this build or on this Mac.",
                                            "Choose a model that runs another way.", _a("choose-model")),
    "memory": lambda *, model, stopped, **_: _row(
        f"This Mac did not have the memory for {model} while this ran{stopped}.",
        "Close other work, or choose a smaller model, then run it again.", _a("choose-model"), _a("retry")),
    "network": lambda *, name, stopped, detail, **_: _row(
        f"Fichero could not reach {name}" + (f" ({detail})" if detail else "") + f"{stopped}.",
        f"Check the connection and {name}'s status, then run it again.", _a("retry")),
    "files-unavailable": lambda *, detail, **_: _row(
        "Some pages' files could not be opened" + (f" ({detail})." if detail else "."),
        "Reconnect the folder, or download the pages from iCloud, then run it again.", _a("reconnect"), _a("retry")),
    "model-broken": lambda *, model, **_: _row(
        f"{model} is on this Mac but could not be loaded.",
        "Download it again in Settings › AI › Local models, or choose another model.",
        _a("open-settings", LOCAL_MODELS_CONTROL), _a("choose-model"), _a("retry")),
    "library-closed": lambda **_: _row(
        "The project was closed while this was running, so the work was paused.",
        "Open the project again; the work continues from where it stopped.", _a("resume")),
    "export-folder-gone": lambda **_: _row(
        "The folder this export writes to is gone.",
        # Choose Folder… moves the export (`PATCH /api/export/kept/{id}`); Continue once the drive is back (#6588).
        "Reconnect the drive, or choose the export's folder again.", _a("choose-folder"), _a("resume")),
    # A run the engine stopping or the project closing left unfinished (#6588): its pages done are kept.
    "interrupted": lambda **_: _row(
        "The run stopped before it finished: the engine stopped, or its project was closed.",
        "Run it again; the pages already done are kept.", _a("retry")),
    "unexpected": lambda *, step, kind_exc, stopped, **_: _row(
        f"Something went wrong inside Fichero while it ran {step} ({kind_exc}){stopped}.",
        "This is a bug in Fichero, not something you did. Send a bug report so it can be fixed; you can also try the run again.",
        _a("report-bug"), _a("retry")),
}

