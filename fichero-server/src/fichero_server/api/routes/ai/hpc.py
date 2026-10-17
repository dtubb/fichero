"""HPC (Slurm) cluster connection routes.

Surfaces an academic HPC/Slurm cluster as a *connection* the app can configure
and test, alongside the LLM provider rows in AI settings. This is the first
slice of the Fichero ⇄ HPC live-connection plan
(``agent-work/design/hpc-slurm-live-connection-plan.md``):

- **Config-first.** A cluster is host alias + username + remote base dir +
  partition/account — a *reference* to the user's own SSH config, never a
  secret (plan §4). Persisted in the app-wide key-value settings table (one
  JSON blob), so no schema migration is needed for the first slice.
- **Test connection.** Builds the ``sinfo`` SSH probe command and returns it;
  actual shell-out is a later wiring step (plan §6 Test-connection button).
- **Dry-run submit.** Assembles the bundle manifest + array sbatch script for a
  workflow run and returns the job spec *without* submitting (plan §2/§3), so
  the whole submission path is inspectable and testable clusterless.

All the heavy lifting is the pure, unit-tested helpers in
``workflows/remote_jobs.py``; this module is a thin HTTP surface over them
following the provider-routes pattern (validate at save time, broadcast a
change event so live clients refresh).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.db.app import AppDatabase
from fichero_server.api.routes.ai.providers import get_app_database
from fichero_server.api.routes.auth.accounts import (
    _require_authenticated_or_bootstrap,
    _require_owner_or_bootstrap,
)
from fichero_server.workflows.remote_jobs import (
    HpcClusterConfig,
    HpcConfigError,
    build_bundle_manifest,
    build_remote_run_spec,
    build_sinfo_probe_command,
)

logger = logging.getLogger(__name__)

# One key-value row holds every configured cluster as a JSON object keyed by
# cluster_id. Cheap, migration-free persistence for the first slice; a
# dedicated table can replace this later without changing the route contract.
_CLUSTERS_SETTING_KEY = "hpc.clusters"


router = APIRouter(dependencies=[Depends(_require_authenticated_or_bootstrap)])


# NOTE: ``get_app_database`` is reused from the provider routes (single source
# of truth) so the same test dependency-override reaches these routes too.


# =============================================================================
# Persistence helpers (app-wide settings blob)
# =============================================================================


def _load_clusters(app_db: AppDatabase) -> dict[str, dict]:
    raw = app_db.get_setting(_CLUSTERS_SETTING_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("hpc: stored clusters blob is not valid JSON; ignoring")
        return {}
    return data if isinstance(data, dict) else {}


def _save_clusters(app_db: AppDatabase, clusters: dict[str, dict]) -> None:
    app_db.set_setting(_CLUSTERS_SETTING_KEY, json.dumps(clusters, sort_keys=True))


def _broadcast_hpc_change() -> None:
    """Fan an HPC config change to every library's change stream (like providers)."""
    try:
        from fichero_server.api.change_stream import emit_change_all_libraries

        emit_change_all_libraries(type="hpc.updated")
    except Exception as exc:  # noqa: BLE001 — a broadcast failure must not fail the write
        logger.warning("hpc: change broadcast failed: %s", exc)


# =============================================================================
# Request / response models
# =============================================================================


class HpcClusterCreate(BaseModel):
    """Configure (create or update) an HPC cluster connection."""

    name: str
    #: Both reach ssh as a bare argument: never start with "-" (an option), no spaces or "@".
    host_alias: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    username: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
    remote_base_dir: str
    partition: str = ""
    account: Optional[str] = None
    ssh_port: int = 22
    #: Omit to create; pass an existing id to update that cluster in place.
    cluster_id: Optional[str] = None


class HpcClusterResponse(BaseModel):
    cluster_id: str
    name: str
    host_alias: str
    username: str
    remote_base_dir: str
    partition: str
    account: Optional[str] = None
    ssh_port: int


class HpcClusterListResponse(BaseModel):
    items: list[HpcClusterResponse]
    count: int


class DeletedResponse(BaseModel):
    status: str


class HpcTestResponse(BaseModel):
    """Result of a (dry-run) Test-connection probe."""

    cluster_id: str
    ok: bool
    #: The argv that WOULD be run to probe the cluster (ssh + sinfo). Returned
    #: so the UI/CLI can show exactly what will execute once shell-out is wired.
    probe_command: list[str]
    detail: str


class HpcDryRunSubmitRequest(BaseModel):
    """Assemble (but do not submit) a workflow run as a Slurm array job."""

    workflow_id: str
    workflow_name: str
    run_id: str
    #: The selected input files (one array index per file). Only the count and
    #: names matter for spec construction; the engine renders/normalizes the
    #: real inputs at staging time.
    input_files: list[str]
    throttle: int = 0
    library_path: str = ""


class HpcDryRunSubmitResponse(BaseModel):
    cluster_id: str
    run_id: str
    remote_workdir: str
    array_directive: str
    task_count: int
    sbatch_script: str


def _to_response(cfg: HpcClusterConfig) -> HpcClusterResponse:
    return HpcClusterResponse(**cfg.to_public_dict())


def _require_cluster(app_db: AppDatabase, cluster_id: str) -> HpcClusterConfig:
    clusters = _load_clusters(app_db)
    raw = clusters.get(cluster_id)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"HPC cluster not found: {cluster_id}")
    return HpcClusterConfig.from_dict(raw)


# =============================================================================
# Routes
# =============================================================================


@router.get("/clusters", response_model=HpcClusterListResponse)
async def list_clusters(
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcClusterListResponse:
    """List configured HPC cluster connections."""
    clusters = _load_clusters(app_db)
    items = [
        _to_response(HpcClusterConfig.from_dict(raw))
        for raw in clusters.values()
    ]
    items.sort(key=lambda c: c.name.lower())
    return HpcClusterListResponse(items=items, count=len(items))


@router.get("/clusters/{cluster_id}", response_model=HpcClusterResponse)
async def get_cluster(
    cluster_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcClusterResponse:
    """Get one HPC cluster connection."""
    return _to_response(_require_cluster(app_db, cluster_id))


@router.post("/clusters", response_model=HpcClusterResponse)
async def create_or_update_cluster(
    request: HpcClusterCreate,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcClusterResponse:
    """Create or update an HPC cluster connection (validated at save time)."""
    cluster_id = request.cluster_id or str(uuid.uuid4())
    cfg = HpcClusterConfig(
        cluster_id=cluster_id,
        name=request.name,
        host_alias=request.host_alias,
        username=request.username,
        remote_base_dir=request.remote_base_dir,
        partition=request.partition,
        account=request.account,
        ssh_port=request.ssh_port,
    )
    try:
        cfg.validate()
    except HpcConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clusters = _load_clusters(app_db)
    clusters[cluster_id] = cfg.to_public_dict()
    _save_clusters(app_db, clusters)
    _broadcast_hpc_change()
    return _to_response(cfg)


@router.delete("/clusters/{cluster_id}", response_model=DeletedResponse)
async def delete_cluster(
    cluster_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> DeletedResponse:
    """Remove an HPC cluster connection."""
    clusters = _load_clusters(app_db)
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail=f"HPC cluster not found: {cluster_id}")
    del clusters[cluster_id]
    _save_clusters(app_db, clusters)
    _broadcast_hpc_change()
    return DeletedResponse(status="deleted")


@router.post("/clusters/{cluster_id}/test", response_model=HpcTestResponse)
async def test_cluster(
    cluster_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcTestResponse:
    """Dry-run Test-connection: build the ``sinfo`` SSH probe command.

    v0 is honest about not executing: it validates the stored config and
    returns the exact argv that a later wiring step will run over the user's
    SSH connection (plan §6). This lets the settings UI show a Test button that
    surfaces the real command today, then flips to live results when shell-out
    lands — no contract change.
    """
    cfg = _require_cluster(app_db, cluster_id)
    try:
        cfg.validate()
    except HpcConfigError as exc:
        return HpcTestResponse(
            cluster_id=cluster_id,
            ok=False,
            probe_command=[],
            detail=f"Config invalid: {exc}",
        )
    command = build_sinfo_probe_command(cfg)
    return HpcTestResponse(
        cluster_id=cluster_id,
        ok=True,
        probe_command=command,
        detail=(
            "Dry-run: SSH reachability + sinfo probe command constructed. "
            "Live execution over your SSH key is wired in a later slice."
        ),
    )


@router.post(
    "/clusters/{cluster_id}/dry-run-submit",
    response_model=HpcDryRunSubmitResponse,
)
async def dry_run_submit(
    cluster_id: str,
    request: HpcDryRunSubmitRequest,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcDryRunSubmitResponse:
    """Assemble a run as a Slurm array job spec WITHOUT submitting (plan §2/§3).

    One workflow run over N input files = one array job with N indices. Returns
    the remote workdir, the ``--array`` directive, and the rendered sbatch
    script so the whole submission path is inspectable before any SSH is wired.
    """
    cfg = _require_cluster(app_db, cluster_id)
    if not request.input_files:
        raise HTTPException(status_code=400, detail="input_files is empty")

    manifest = build_bundle_manifest(
        workflow_id=request.workflow_id,
        workflow_name=request.workflow_name,
        input_files=request.input_files,
        library_path=request.library_path or "",
        run_id=request.run_id,
        metadata={"execution_site": "hpc/slurm", "cluster": cfg.name},
    )
    try:
        spec = build_remote_run_spec(
            cluster=cfg,
            manifest=manifest,
            input_indices=list(range(len(request.input_files))),
            throttle=request.throttle,
        )
    except HpcConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return HpcDryRunSubmitResponse(
        cluster_id=cluster_id,
        run_id=request.run_id,
        remote_workdir=spec.remote_workdir,
        array_directive=spec.array_directive,
        task_count=len(request.input_files),
        sbatch_script=spec.sbatch_script,
    )


# =============================================================================
# Sign-in: the cluster's key and the second factor (#5238)
# =============================================================================


class HpcKeyPush(BaseModel):
    private_key: str = Field(min_length=1, max_length=20000, description="The key the app holds in its Keychain.")


class HpcKeyState(BaseModel):
    cluster_id: str
    has_key: bool


class HpcPrompt(BaseModel):
    id: str
    prompt: str = Field(description="The far side's own prompt text, as ssh asked it.")


class HpcPromptList(BaseModel):
    items: list[HpcPrompt]


class HpcPromptAnswer(BaseModel):
    answer: str = Field(description="Passed to ssh and kept nowhere.")


@router.put("/clusters/{cluster_id}/key", response_model=HpcKeyState)
async def put_cluster_key(
    cluster_id: str,
    body: HpcKeyPush,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcKeyState:
    """The app pushes the cluster's private key into the engine's own folder; it is never read back."""
    from fichero_server.remote_read.ssh_prompts import store_cluster_key

    _require_cluster(app_db, cluster_id)
    try:
        store_cluster_key(cluster_id, body.private_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HpcKeyState(cluster_id=cluster_id, has_key=True)


@router.delete("/clusters/{cluster_id}/key", response_model=HpcKeyState)
async def delete_cluster_key(
    cluster_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> HpcKeyState:
    from fichero_server.remote_read.ssh_prompts import remove_cluster_key

    try:
        remove_cluster_key(cluster_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HpcKeyState(cluster_id=cluster_id, has_key=False)


@router.get("/prompts", response_model=HpcPromptList)
async def list_prompts(_owner: None = Depends(_require_owner_or_bootstrap)) -> HpcPromptList:
    """What a cluster login is waiting on (a second factor, a passphrase), for the app to show."""
    from fichero_server.remote_read.ssh_prompts import prompt_broker

    return HpcPromptList(items=[HpcPrompt(**p) for p in prompt_broker().pending()])


@router.post("/prompts/{prompt_id}", response_model=HpcPromptList)
async def answer_prompt(
    prompt_id: str,
    body: HpcPromptAnswer,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> HpcPromptList:
    from fichero_server.remote_read.ssh_prompts import prompt_broker

    broker = prompt_broker()
    if not broker.answer(prompt_id, body.answer):
        if broker.ended(prompt_id) == "expired":
            raise HTTPException(status_code=410, detail="That prompt expired before it was answered: sign in again.")
        if broker.ended(prompt_id) == "refused":
            raise HTTPException(status_code=410, detail="That prompt was refused: sign in again.")
        raise HTTPException(status_code=404, detail="no such prompt (already answered)")
    return await list_prompts(None)


@router.post("/clusters/{cluster_id}/sign-in", response_model=HpcKeyState)
async def sign_in(
    cluster_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcKeyState:
    """Open the one connection to the cluster. ssh's prompts come out of `GET /prompts` for the app to answer;
    the call returns when the connection is open or the attempt ended (typed reason)."""
    import asyncio

    from fichero_server.remote_read.slurm_target import NoKey, SlurmError, SshShell
    from fichero_server.remote_read.ssh_prompts import cluster_key_path, control_dir, prompt_broker

    cfg = _require_cluster(app_db, cluster_id)
    try:
        shell = SshShell(cfg, cluster_key_path(cluster_id), control_dir())
    except NoKey as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        await asyncio.to_thread(shell.open_master, prompts=prompt_broker())
    except SlurmError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return HpcKeyState(cluster_id=cluster_id, has_key=True)


class HpcCheckStep(BaseModel):
    name: str
    state: str = Field(description="`passed`, `failed` (with its reason in `answer`) or `not tried`.")
    answer: str = ""


class HpcCheckResponse(BaseModel):
    cluster_id: str
    ok: bool = Field(description="True only if every step passed just now.")
    steps: list[HpcCheckStep]


def _shell_for(cfg: HpcClusterConfig, cluster_id: str):
    """The login shell for a stored cluster, over the connection `sign-in` opened (BatchMode: it never asks)."""
    from fichero_server.remote_read.slurm_target import NoKey, SshShell
    from fichero_server.remote_read.ssh_prompts import cluster_key_path, control_dir

    try:
        return SshShell(cfg, cluster_key_path(cluster_id), control_dir())
    except NoKey as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/clusters/{cluster_id}/check", response_model=HpcCheckResponse)
async def check_cluster_live(
    cluster_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> HpcCheckResponse:
    """The honest check (`compute.connect.check-really-checks`): hostname, storage, Apptainer, GPUs and fair share,
    run live on the login node over the open connection. Sign in first; nothing is submitted."""
    import asyncio

    from fichero_server.remote_read.cluster_check import check_cluster

    cfg = _require_cluster(app_db, cluster_id)
    result = await asyncio.to_thread(check_cluster, _shell_for(cfg, cluster_id))
    return HpcCheckResponse(cluster_id=cluster_id, **result)
