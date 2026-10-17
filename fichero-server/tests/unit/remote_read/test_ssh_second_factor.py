"""The second factor and the key, for the cluster login (`compute.connect.second-factor-passes-through`,
`compute.connect.ssh-in-process`): a fake `ssh` stands in for the far side."""
from __future__ import annotations

import stat
import threading

import pytest

from fichero_server.remote_read.slurm_target import SlurmError, SshShell
from fichero_server.remote_read.ssh_prompts import (
    PromptBroker,
    SecondFactorRefused,
    cluster_key_path,
    remove_cluster_key,
    store_cluster_key,
)
from fichero_server.workflows.remote_jobs import HpcClusterConfig

CLUSTER = HpcClusterConfig(cluster_id="rorqual", name="Rorqual", host_alias="rorqual", username="u",
                           remote_base_dir="/project/def-lab/u", account="def-lab")

# Asks the way ssh does (runs $SSH_ASKPASS with the prompt as its argument); right answer 123456 connects.
FAKE_SSH = """#!/bin/sh
case " $* " in *" BatchMode=yes "*) echo "BATCH" > "$0.batch" ;; esac
answer=$("$SSH_ASKPASS" "Duo passcode or option (1-3): ") || exit 255
[ "$answer" = "123456" ] || exit 255
exit 0
"""


def _fake_ssh(tmp_path):
    fake = tmp_path / "fakessh"
    fake.write_text(FAKE_SSH)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return fake


def _shell(tmp_path):
    key = tmp_path / "id"
    key.write_text("k")
    return SshShell(CLUSTER, key, tmp_path, ssh=str(_fake_ssh(tmp_path)))


def _answer_when_asked(broker, text):
    def run():
        while not (pending := broker.pending()):
            threading.Event().wait(0.01)
        broker.answer(pending[0]["id"], text)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def test_ssh_prompt_text_reaches_the_app_and_the_answer_connects_without_batch_mode(tmp_path):
    """WHY: BatchMode forbids asking, so the master is opened without it; ssh's own prompt is shown, not ours."""
    broker = PromptBroker()
    shell = _shell(tmp_path)
    seen = []
    thread = _answer_when_asked(broker, "123456")
    orig = broker.ask
    broker.ask = lambda prompt, **kw: (seen.append(prompt), orig(prompt, **kw))[1]
    shell.open_master(prompts=broker, timeout=10)
    thread.join(5)
    assert seen == ["Duo passcode or option (1-3): "]
    assert not (tmp_path / "fakessh.batch").exists()
    assert broker.pending() == []  # nothing is kept once answered


def test_a_wrong_answer_or_a_refusal_is_a_typed_failure(tmp_path):
    broker = PromptBroker()
    thread = _answer_when_asked(broker, "000000")
    with pytest.raises(SlurmError, match="could not connect"):
        _shell(tmp_path).open_master(prompts=broker, timeout=10)
    thread.join(5)

    def refuse():
        while not (pending := broker.pending()):
            threading.Event().wait(0.01)
        broker.refuse(pending[0]["id"])

    t = threading.Thread(target=refuse, daemon=True)
    t.start()
    with pytest.raises(SlurmError):
        _shell(tmp_path).open_master(prompts=broker, timeout=10)


def test_an_unanswered_prompt_times_out_naming_the_reason():
    with pytest.raises(SecondFactorRefused, match="no answer"):
        PromptBroker().ask("Duo passcode: ", timeout=0.05)


def test_the_key_lives_in_the_engine_folder_privately_and_goes_with_the_target(tmp_path, monkeypatch):
    """WHY (`compute.secret.fichero-makes-the-key`): the app pushes the Keychain key to the engine; no ~/.ssh."""
    monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
    path = store_cluster_key("rorqual", "-----BEGIN OPENSSH PRIVATE KEY-----\nk\n")
    assert path == cluster_key_path("rorqual") and path.read_text().endswith("k\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    remove_cluster_key("rorqual")
    assert not path.exists()
    for bad in ("../x", "a/b", "", ".hidden", "-oProxyCommand"):
        with pytest.raises(ValueError):
            store_cluster_key(bad, "k")


def test_the_connection_folder_is_ours_private_and_not_a_symlink(tmp_path, monkeypatch):
    """WHY (review 41): a folder any local user could pre-create would let them sit in front of the open connection."""
    import os

    from fichero_server.remote_read import ssh_prompts

    monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
    path = ssh_prompts.control_dir()
    assert stat.S_IMODE(path.stat().st_mode) == 0o700 and path.stat().st_uid == os.getuid() and not path.is_symlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(ssh_prompts, "_control_candidates", lambda: [tmp_path / "link"])
    (tmp_path / "link").symlink_to(elsewhere)
    with pytest.raises(PermissionError, match="symlink"):
        ssh_prompts.control_dir()
    monkeypatch.setattr(ssh_prompts, "_owner", lambda st: os.getuid() + 1)
    (tmp_path / "link").unlink()
    with pytest.raises(PermissionError, match="owned by another user"):
        ssh_prompts.control_dir()


def test_the_askpass_wrapper_quotes_its_paths(tmp_path, monkeypatch):
    from fichero_server.remote_read import ssh_prompts

    monkeypatch.setattr(ssh_prompts.sys, "executable", "/opt/my python/bin/python")
    server = ssh_prompts.AskpassServer(PromptBroker())
    try:
        wrapper = server.env()["SSH_ASKPASS"]
        assert "'/opt/my python/bin/python'" in open(wrapper).read()
    finally:
        server.close()


def test_an_answer_that_comes_too_late_is_told_it_expired_not_unknown():
    """WHY (review 49): the person typed the code after the prompt timed out; saying nothing, or "unknown", hides why."""
    broker = PromptBroker()
    with pytest.raises(SecondFactorRefused):
        broker.ask("Duo passcode: ", timeout=0.05)
    assert broker.answer("1", "123456") is False
    assert broker.ended("1") == "expired" and broker.ended("999") is None
    thread = threading.Thread(target=lambda: pytest.raises(SecondFactorRefused, broker.ask, "x", timeout=5), daemon=True)
    thread.start()
    while not (pending := broker.pending()):
        threading.Event().wait(0.01)
    broker.refuse(pending[0]["id"])
    thread.join(5)
    assert broker.ended(pending[0]["id"]) == "refused"


def test_a_sign_in_that_timed_out_on_the_prompt_says_expired(tmp_path):
    broker = PromptBroker()  # nobody answers
    with pytest.raises(SlurmError, match="expired"):
        _shell(tmp_path).open_master(prompts=broker, timeout=3)
