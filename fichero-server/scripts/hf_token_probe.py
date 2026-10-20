#!/usr/bin/env python3
"""What the Hugging Face token Fichero holds can do (#5894), asked the engine's way and READ-ONLY: `whoami` only. Nothing is created,
uploaded or started. Logs the username and the token's role / fine-grained permissions (never the token) and answers in words:
can it create a PRIVATE dataset repo in the owner's namespace, and can it start Jobs.

  python fichero-server/scripts/hf_token_probe.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _harness():
    path = Path(__file__).with_name("ab_kraken_cloud.py")
    spec = importlib.util.spec_from_file_location("ab_kraken_cloud", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    from huggingface_hub import HfApi

    from fichero_server.security.keychain import ProviderKeyState, lookup_api_key
    from fichero_server.training import hf_jobs

    token = None
    answer = lookup_api_key("huggingface")
    if answer.state is ProviderKeyState.FOUND:
        token, source = answer.key, "the keychain (the app's item)"
    else:
        if answer.state is ProviderKeyState.UNREADABLE:
            print(f"KEYCHAIN: the app's huggingface item exists but this process cannot read it ({answer.detail or 'no detail'}): "
                  "locked, or over SSH there is no session to unlock it, or the item belongs to the app and a plain python process "
                  "is not trusted by it.")
        else:
            print("KEYCHAIN: no huggingface item.")
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
        source = "the environment"
        if not token:
            found = _harness().read_env_file(Path("~/.config/fichero/ab.env"))
            token, source = found.get("HF_TOKEN") or found.get("HUGGINGFACE_API_KEY"), "the key file"
        if not token:
            print("TOKEN: none readable here (keychain, environment, ab.env). Nothing checked.")
            return 2
    print(f"TOKEN: found in {source}")
    me = HfApi().whoami(token=token)
    access = (me.get("auth") or {}).get("accessToken") or {}
    role = access.get("role")
    grants = access.get("fineGrained") or {}
    print(f"USER: {me.get('name')}  token name: {access.get('displayName')}  role: {role}")
    if role == "fineGrained":
        print(f"  global permissions: {sorted(grants.get('global') or [])}")
        for scoped in grants.get("scoped") or []:
            print(f"  on {(scoped.get('entity') or {}).get('type')} {(scoped.get('entity') or {}).get('name')}: "
                  f"{sorted(scoped.get('permissions') or [])}")
    lacking = hf_jobs._lacks(me)
    mine = {p for s in (grants.get("scoped") or []) if (s.get("entity") or {}).get("name") == me.get("name")
            for p in (s.get("permissions") or [])} | set(grants.get("global") or [])
    can_repo = role in ("write", "admin") or "repo.write" in mine
    can_jobs = not lacking or "job.write" in mine
    print(f"ENGINE CHECK needs {list(hf_jobs.NEEDED_PERMISSIONS)}; missing: {lacking or 'nothing'}")
    print("PRIVATE DATASET in " + str(me.get("name")) + ": " + ("YES (write access to the namespace's repos)" if can_repo
          else "NO: the token has no write permission on repos in this namespace"))
    print("START JOBS: " + ("YES" if can_jobs else "NO or not shown by the token's data: " + (", ".join(lacking) or "see permissions above")))
    print("Nothing was created, uploaded or started.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
