"""Chat tools generated from the action registry (#2016 / #1847).

Every registered :class:`fichero_server.actions.registry.ActionRegistration` becomes one
OpenAI / LiteLLM *function tool* the chat agent can call. This is the LiteLLM-
shaped projection of the SAME registry already exposed over HTTP by
``GET /api/actions/registry`` + ``POST /api/actions/invoke`` (see
``api/routes/actions_registry.py``) — one definition, reached five ways
(UI · chat tools · App Intents · tests · audit), per EPIC #1848.

Two public entry points:

* :func:`action_tools` — ``list[dict]`` of LiteLLM/OpenAI tool definitions, one
  per registered action. Drop straight into a ``tools=[...]`` kwarg.
* :func:`dispatch_tool_call` — given a tool name + arguments a model emitted,
  run the matching action through the audited ``registry.invoke`` choke point
  (actor='chat', ``origin_window`` threaded through) and return the
  :class:`ActionResult`.

**Name mapping.** Registry names are ``<domain>.<verb>`` (dotted); OpenAI tool
names must match ``^[a-zA-Z0-9_-]+$``. :func:`tool_name_for` sanitises ``.``/``:``
(and any other illegal char) to ``_``; dispatch resolves the model's tool name
back to the canonical action name by scanning the registry, so the lossy
transform never has to be reversed.

**Wiring status (reported, NOT auto-enabled).** The live ``POST /api/chat``
endpoint (``api/routes/chat.py``) is single-shot RAG — ``llm.invoke(prompt)`` with
no tool-calling loop and therefore no ``tools=[...]`` list to extend. Turning the
chat endpoint into an agentic loop is a deliberate, separate change; this module
provides the generator + dispatcher so that flip is a small, safe edit rather
than a risky rewire. See the module's ``# WIRING`` note below.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any

from fichero_server.actions.registry import (
    ActionContext,
    ActionNotFoundError,
    ActionRegistration,
    ActionRegistry,
    ActionResult,
    registry as _global_registry,
)

logger = logging.getLogger(__name__)

# OpenAI / LiteLLM require tool names to match this; the registry's dotted
# `<domain>.<verb>` names do not.
_ILLEGAL_TOOL_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def tool_name_for(action_name: str) -> str:
    """Map a registry action name (``<domain>.<verb>``) to a valid tool name.

    ``claim.create`` -> ``claim_create``; ``classification:rename`` ->
    ``classification_rename``. Any character outside ``[a-zA-Z0-9_-]`` becomes
    ``_``. The transform is lossy (dots and colons collapse to the same ``_``),
    so callers resolve back via :func:`resolve_action_name`, never by inverting.
    """
    return _ILLEGAL_TOOL_NAME_CHARS.sub("_", action_name)


def _tool_description(action: ActionRegistration) -> str:
    """Best available human description for an action.

    Preference order: the ``execute`` callable's docstring, then the params
    model's docstring (most actions document the request shape there, e.g.
    ``ClaimCreateRequest`` -> "Request to create a knowledge claim."), then a
    generated fallback so the field is never empty (OpenAI rejects blank ones).
    Only the first paragraph is kept — tool descriptions want a one-liner.
    """
    # NB: use the params model's OWN __doc__ (not inspect.getdoc, which walks the
    # MRO and would return Pydantic's BaseModel docstring for a model that defines
    # none). cls.__doc__ is None when the subclass has no docstring of its own.
    model_doc = action.params_model.__doc__
    doc = inspect.getdoc(action.execute) or (
        inspect.cleandoc(model_doc) if model_doc else None
    )
    if doc:
        first_para = doc.strip().split("\n\n", 1)[0].strip()
        if first_para:
            return first_para
    return f"Invoke the '{action.name}' action."


def action_tool(action: ActionRegistration) -> dict:
    """Build one OpenAI/LiteLLM tool definition for a single registered action.

    Shape::

        {"type": "function",
         "function": {"name": <sanitised>, "description": <doc>,
                      "parameters": <params_model JSON schema>}}
    """
    return {
        "type": "function",
        "function": {
            "name": tool_name_for(action.name),
            "description": _tool_description(action),
            "parameters": action.params_model.model_json_schema(),
        },
    }


def action_tools(
    reg: ActionRegistry | None = None, *, read_only: bool = False
) -> list[dict]:
    """Return one LiteLLM/OpenAI tool definition per registered action.

    Reads the process-global :data:`fichero_server.actions.registry.registry` unless an
    explicit registry is passed (tests). Order follows ``registry.all()`` (sorted
    by action name) so the tool list is stable across calls.

    ``read_only=True`` filters the list to actions flagged
    :attr:`ActionRegistration.read_only` — the safe subset the chat-tools agent
    loop (#1847) is allowed to call this slice; every mutating action is withheld
    from the model entirely (defence-in-depth alongside the dispatch gate).

    NOTE: actions register at import time via the ``@action`` decorator on the
    route modules, which ``api/main.py`` imports at app startup — so by the time
    the chat agent runs, the registry is fully populated. In a bare test, import
    the relevant route module(s) first to populate it.
    """
    reg = reg or _global_registry
    actions = reg.all()
    if read_only:
        actions = [action for action in actions if action.read_only]
    return [action_tool(action) for action in actions]


def is_read_only_action(tool_name: str, reg: ActionRegistry | None = None) -> bool:
    """True when ``tool_name`` resolves to an action flagged ``read_only``.

    Accepts either the sanitised tool name or the canonical action name. Raises
    :class:`ActionNotFoundError` if the name matches no registered action — the
    caller decides whether an unknown tool is an error (it is, for chat).
    """
    reg = reg or _global_registry
    action_name = resolve_action_name(tool_name, reg)
    return bool(reg.get(action_name).read_only)


def available_tool_names(reg: ActionRegistry | None = None) -> list[str]:
    """Sanitised tool names for every registered action (handy for prompts/logs)."""
    reg = reg or _global_registry
    return [tool_name_for(name) for name in reg.names()]


def resolve_action_name(tool_name: str, reg: ActionRegistry | None = None) -> str:
    """Resolve a model-emitted tool name back to a canonical registry action name.

    Accepts either the exact action name (``claim.create``) or its sanitised tool
    form (``claim_create``). Raises :class:`ActionNotFoundError` if neither
    matches a registered action.
    """
    reg = reg or _global_registry
    # Fast path: the model echoed the exact action name.
    try:
        reg.get(tool_name)
        return tool_name
    except ActionNotFoundError:
        pass
    # Otherwise match on the sanitised form.
    for name in reg.names():
        if tool_name_for(name) == tool_name:
            return name
    raise ActionNotFoundError(tool_name)


def dispatch_tool_call(
    db: Any,
    tool_name: str,
    arguments: dict | str | None,
    *,
    actor: str = "chat",
    origin_window: str | None = None,
    run_id: str | None = None,
    library_path: str | None = None,
    reg: ActionRegistry | None = None,
) -> ActionResult:
    """Run a model-requested tool call through the audited action choke point.

    Mirrors ``POST /api/actions/invoke`` but for the chat agent: resolves the
    tool name to an action, builds an :class:`ActionContext` (``actor='chat'`` by
    default, ``origin_window`` threaded through for the change stream's self-echo
    de-dup), and calls :meth:`ActionRegistry.invoke` — which validates params,
    executes, writes the :class:`ActionAudit` row, and emits the change event.

    ``arguments`` may be a dict or the raw JSON string LiteLLM/OpenAI delivers in
    ``tool_call.function.arguments``; a string is parsed (empty/None -> ``{}``).
    Returns the :class:`ActionResult` (``ok``, ``result``, ``audit_id``,
    ``changed_domains``) — the caller serialises it back as the tool's result
    message.
    """
    reg = reg or _global_registry
    if isinstance(arguments, str):
        arguments = json.loads(arguments) if arguments.strip() else {}
    elif arguments is None:
        arguments = {}

    action_name = resolve_action_name(tool_name, reg)
    ctx = ActionContext(
        actor=actor,
        origin_window=origin_window,
        run_id=run_id,
        library_path=library_path,
    )
    logger.debug(
        "chat tool dispatch: tool=%s -> action=%s actor=%s", tool_name, action_name, actor
    )
    return reg.invoke(db, action_name, arguments, ctx)


# ===========================================================================
# WIRING — now live behind a flag (#1847 / #3)
# ===========================================================================
#
# The chat agent loop is wired into `POST /api/chat`
# (`api/routes/system/chat.py::_run_chat_tools_loop`), DEFAULT-OFF behind the
# `FICHERO_CHAT_TOOLS` env flag. When the flag is off the endpoint stays
# single-shot RAG, byte-for-byte unchanged. When on, the handler:
#
#     from fichero_server.actions.chat_tools import (
#         action_tools, is_read_only_action, dispatch_tool_call,
#     )
#
#     tools = action_tools(read_only=True)          # SAFE subset only (this slice)
#     resp = await llm.bind_tools(tools).ainvoke(messages)
#     for call in resp.tool_calls:                   # agent asked to act
#         if not is_read_only_action(call["name"]):  # deny mutations, don't invoke
#             record denied tool_call; continue
#         result = dispatch_tool_call(db, call["name"], call["args"], actor="chat", ...)
#     # loop until the model stops emitting tool calls (bounded max-iterations).
#
# READS-ONLY THIS SLICE: only actions flagged `read_only=True` are exposed AND
# dispatched. Mutating tool calls are refused (recorded as a denied `tool_call`,
# never invoked) so no write can reach `registry.invoke` from chat until a later
# write-policy review lands (EPIC #1848). Every dispatched read still flows
# through the audited `registry.invoke` choke point — one path, one audit.
