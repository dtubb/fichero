"""What provider will this workflow ACTUALLY call, and will it cost money (#4503).

A preset declares a *tier*. The app database decides the *provider*. Nothing in
the preset records which one you get, so "is this workflow free?" is not
answerable from the file — it is a property of preset **plus** database, and
that gap is denominated in money. It cost real money twice on 2026-08-03: once
from a probe expected to be on-device that went to OpenRouter, and once from a
triage that classified presets as free by reading their JSON.

Neither mistake was careless. The answer was never in the file either reader
was reading. This module puts it somewhere it can be read.

Two rules it is built on:

**It never makes a call.** Everything here is configuration resolution. A cost
preview that costs money would be self-defeating.

**It reuses the runner's own resolution, never a copy of it.** The answer comes
from ``_resolve_node_llm_config_inner`` — the same function the builder uses to
decide what to call — so a preview cannot drift from the run it describes. A
second implementation of that precedence would eventually disagree, and a
resolver that disagrees with the runner is worse than none: authoritative
looking, and wrong.

Only the *provenance* label is derived here, by inspecting the same inputs the
resolver saw. That is deliberate: the answer (which provider) is authoritative
because it is the real one; the label (where it came from) is this module's own
reading, and the tests check the two agree.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fichero_server.llm import LLMConfig


class ResolutionSource(str, Enum):
    """Which layer supplied the provider — the half that makes it a surprise.

    "openrouter, pinned on the node" and "openrouter, inherited from the app
    database" are different facts. Only the second one is a surprise, and only
    the second one is invisible to someone reading the preset. Reporting the
    answer without the source would reproduce the original defect one level up.
    """

    node = "node"
    """Pinned on the node itself. Visible to anyone reading the preset."""

    workflow = "workflow"
    """The workflow's own default. Visible in the preset's top-level config."""

    profile = "profile"
    """A named model profile the node references."""

    env = "env"
    """A FICHERO_<TIER>_PROVIDER + _MODEL pair. Beats the database.

    Both must be set: `resolve_model_alias` ignores the pair unless provider
    AND model are present, so setting only one looks like a pin and is not.
    """

    app_db = "app_db"
    """The app database's `default_<tier>_*` settings. INVISIBLE in the preset.

    This is the layer that cost money. A node with no provider is not
    unconfigured — it is configured somewhere the preset's reader cannot see.
    """

    none = "none"
    """This node calls no model at all. Free under every configuration."""

    unresolved = "unresolved"
    """Resolution raised. Reported, never guessed — an unresolvable node is a
    run that will fail, and saying "free" about it would be a third lie."""


@dataclass(frozen=True)
class NodeProviderResolution:
    """What one node would really call."""

    node_id: str
    tool: str
    uses_model: bool
    tier_requested: str | None
    provider: str | None
    model: str | None
    source: ResolutionSource
    billable: bool | None
    error: str | None = None

    @property
    def is_surprise(self) -> bool:
        """Billable, and not visible to someone reading the preset.

        The exact shape that cost money twice: nothing in the JSON says paid,
        and the run bills anyway.
        """
        return bool(self.billable) and self.source in {
            ResolutionSource.app_db,
            ResolutionSource.env,
        }


@dataclass(frozen=True)
class WorkflowProviderPreview:
    """What a whole workflow would really call. Nothing was executed."""

    workflow_name: str
    nodes: list[NodeProviderResolution] = field(default_factory=list)

    @property
    def billable_nodes(self) -> list[NodeProviderResolution]:
        return [n for n in self.nodes if n.billable]

    @property
    def unresolved_nodes(self) -> list[NodeProviderResolution]:
        """Nodes whose provider could not be established — by error OR by absence.

        `ResolutionSource.unresolved` is only set when resolution RAISES. A
        resolution that succeeds while producing a config with no provider took
        the ordinary path, so it was not counted here, and
        `_provider_is_billable(None)` answered False — not billable, therefore
        free. A node whose provider nobody can name was reported as costing
        nothing, which is this module's own defect one level in.

        Both are the same fact: we cannot say what this node will call. The rule
        this module states about itself has to hold whichever way the provider
        went missing.
        """
        return [
            n
            for n in self.nodes
            if n.source is ResolutionSource.unresolved
            or (n.uses_model and not n.provider)
        ]

    @property
    def would_cost_money(self) -> bool:
        return bool(self.billable_nodes)

    @property
    def is_free(self) -> bool:
        """Free AND fully resolvable.

        An unresolved node is not free — it is unknown, and reporting unknown
        as free is how this class of defect recurs.
        """
        return not self.would_cost_money and not self.unresolved_nodes

    @property
    def surprises(self) -> list[NodeProviderResolution]:
        return [n for n in self.nodes if n.is_surprise]

    def summary(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow_name,
            "free": self.is_free,
            "would_cost_money": self.would_cost_money,
            "billable_nodes": len(self.billable_nodes),
            "unresolved_nodes": len(self.unresolved_nodes),
            "surprises": len(self.surprises),
            "providers": sorted(
                {n.provider for n in self.nodes if n.provider} - {None}
            ),
        }


def _provider_is_billable(provider: str | None) -> bool:
    """True when calling this provider spends money.

    Delegates to the same provider registry the local-only enforcement uses
    (`is_local` / `is_builtin`) rather than carrying a list of paid provider
    names. A hand-maintained list here would be a second source of truth about
    which providers cost money, and the first one to go stale.
    """
    if not provider:
        return False
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info(provider.strip().lower())
    if info is None:
        # An unknown provider is treated as billable. If we cannot establish
        # that something is on-device, saying "free" is the expensive guess.
        return True
    return not (info.is_local or info.is_builtin)


def _requested_tier(node_def: Any, workflow_config: LLMConfig) -> tuple[str | None, ResolutionSource]:
    """What the node asked for, and which layer asked it.

    Inspection only — mirrors the branch order of
    ``_resolve_node_llm_config_inner`` without re-deciding anything. The
    authoritative answer still comes from that function.
    """
    cfg = getattr(node_def, "config", None) or {}
    if (
        cfg.get("model_profile_id")
        or cfg.get("profile_id")
        or cfg.get("model_profile")
    ):
        return (str(cfg.get("model_profile_id") or cfg.get("profile_id") or cfg.get("model_profile")), ResolutionSource.profile)

    node_provider = getattr(node_def, "provider_name", None) or cfg.get("provider_name", "")
    node_model = getattr(node_def, "model_name", None) or cfg.get("model_name", "")
    if node_provider or node_model:
        requested = str(node_provider or node_model)
        if requested.startswith("$"):
            # A tier alias: the node names a TIER, not a provider. Which layer
            # answers it is decided below, in _alias_source.
            return (requested, _alias_source(requested))
        return (requested, ResolutionSource.node)

    if getattr(workflow_config, "provider", None):
        return (workflow_config.provider, ResolutionSource.workflow)

    # No provider anywhere in the preset. This is the majority case and the
    # one that cost money: the app database answers, invisibly.
    return (None, ResolutionSource.app_db)


def _alias_source(alias: str) -> ResolutionSource:
    """Env or database — for an alias, whichever `resolve_model_alias` uses.

    Both env vars must be present or the pair is ignored, so this checks both.
    """
    import os

    tier = alias[1:].upper()
    if os.environ.get(f"FICHERO_{tier}_PROVIDER") and os.environ.get(f"FICHERO_{tier}_MODEL"):
        return ResolutionSource.env
    return ResolutionSource.app_db


def resolve_node_provider(
    node_def: Any, workflow_config: LLMConfig
) -> NodeProviderResolution:
    """What this ONE node would really call. Makes no request."""
    from fichero_server.workflows.builder import _resolve_node_llm_config_inner
    from fichero_server.workflows.registry import get_tool_def

    tool = getattr(node_def, "tool", "") or ""
    node_id = getattr(node_def, "id", "") or ""
    tool_def = get_tool_def(tool)

    # Delegation: the node calls no model ITSELF, but the workflow it delegates
    # to may call many. Reporting that as "no model" would produce a confident
    # "free" for a preset whose entire cost lives in a child — the same defect
    # this module exists to stop, one level down. Reported as unresolved, which
    # is not free, because unknown is the honest answer until the child is
    # followed too.
    if tool == "sub_workflow":
        return NodeProviderResolution(
            node_id=node_id, tool=tool, uses_model=True, tier_requested=None,
            provider=None, model=None, source=ResolutionSource.unresolved,
            billable=None,
            error=(
                "delegates to a sub-workflow; this preview does not follow "
                "delegation, so the cost of the child is unknown from here"
            ),
        )

    # A node that calls no model is free under EVERY configuration — the only
    # thing in this system that can honestly be called free from the file alone.
    if not (tool_def and getattr(tool_def, "uses_llm", False)):
        return NodeProviderResolution(
            node_id=node_id, tool=tool, uses_model=False, tier_requested=None,
            provider=None, model=None, source=ResolutionSource.none, billable=None,
        )

    tier, source = _requested_tier(node_def, workflow_config)

    try:
        resolved: LLMConfig = _resolve_node_llm_config_inner(node_def, workflow_config)
    except Exception as exc:
        return NodeProviderResolution(
            node_id=node_id, tool=tool, uses_model=True, tier_requested=tier,
            provider=None, model=None, source=ResolutionSource.unresolved,
            billable=None, error=f"{type(exc).__name__}: {exc}",
        )

    provider = getattr(resolved, "provider", None)
    model = getattr(resolved, "model", None)
    return NodeProviderResolution(
        node_id=node_id, tool=tool, uses_model=True, tier_requested=tier,
        provider=provider, model=model, source=source,
        billable=_provider_is_billable(provider),
    )


def preview_workflow_providers(
    workflow_def: Any, *, workflow_config: LLMConfig | None = None
) -> WorkflowProviderPreview:
    """What a whole workflow would really call. Executes nothing.

    ``workflow_def`` is a runtime ``WorkflowDef`` (from ``to_workflow_def``),
    so this describes exactly the shape the builder is handed.
    """
    cfg = workflow_config or LLMConfig(
        provider=getattr(workflow_def, "provider", "") or "",
        model=getattr(workflow_def, "model", "") or "",
    )
    return WorkflowProviderPreview(
        workflow_name=getattr(workflow_def, "name", "") or "",
        nodes=[
            resolve_node_provider(node, cfg)
            for node in (getattr(workflow_def, "nodes", None) or [])
        ],
    )


class _ExplicitDefaults:
    """An app-database stand-in built from a tier->(provider, model) mapping.

    Exists so a preview can describe a configuration OTHER than this process's
    own — specifically the SERVER's, fetched over HTTP. Without it the only way
    to answer "what will the server call?" is to read the local app database
    and hope the two match, which is the assumption that cost money twice.

    It answers the same three questions `_resolve_node_llm_config_inner` asks
    of the real app database, so the resolution path is unchanged; only where
    the defaults come from differs.
    """

    def __init__(self, defaults: dict[str, str]):
        self._defaults = {k: v for k, v in (defaults or {}).items() if v}

    def get_setting(self, key: str):
        return self._defaults.get(key)

    def get_default_model_for_category(self, category: str):
        provider = self._defaults.get(f"default_{category}_provider") or self._defaults.get(
            "default_vision_provider" if category == "vision" else "default_text_provider"
        )
        model = self._defaults.get(f"default_{category}_model") or self._defaults.get(
            "default_vision_model" if category == "vision" else "default_text_model"
        )
        return (provider, model) if provider and model else None

    def get_default_model(self):
        provider = self._defaults.get("default_text_provider")
        model = self._defaults.get("default_text_model")
        return (provider, model) if provider and model else None

    def list_providers(self):
        return []

    def list_models(self, _provider_id):
        return []


@contextmanager
def using_defaults(defaults: dict[str, str] | None):
    """Resolve against ``defaults`` instead of this process's app database.

    A context manager rather than a parameter threaded through every function:
    the defaults are consumed deep inside the runner's own resolver, and
    passing them down would mean forking that function — the one thing this
    module must not do, because a preview that disagrees with the runner is
    worse than none.
    """
    if not defaults:
        yield
        return

    import fichero_server.db.app as app_module

    original = app_module.get_app_db
    stand_in = _ExplicitDefaults(defaults)
    app_module.get_app_db = lambda: stand_in
    try:
        yield
    finally:
        app_module.get_app_db = original


def preview_preset_providers(preset: dict) -> WorkflowProviderPreview:
    """Same, for a shipped preset dict straight off disk."""
    from fichero_server.models import Workflow
    from fichero_server.workflows.runtime import to_workflow_def

    wf = to_workflow_def(
        Workflow(
            id=f"preview-{preset.get('name', '')}",
            name=preset.get("name", ""),
            nodes=preset.get("nodes", []),
            edges=preset.get("edges", []),
            config=preset.get("config", {}) or {},
            folder_path=preset.get("folder_path", "/"),
        )
    )
    return preview_workflow_providers(wf)
