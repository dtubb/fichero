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

    from fichero_server.training import hf_jobs

    try:
        source = _harness().ensure_provider_key("huggingface")  # the engine's lookup, in words, then the key file
    except SystemExit as exc:
        print(f"TOKEN: {exc}. Nothing checked.")
        return 2
    from fichero_server.llm import get_api_key

    token = get_api_key("huggingface")
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
