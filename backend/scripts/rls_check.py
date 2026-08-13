"""Verify row-level security against a real Postgres, with one command.

    uv run python -m scripts.rls_check

Brings up the local Supabase stack if it is not already running, applies the
migrations, creates two throwaway users, and runs `tests/integration/
test_rls_live.py` against them. Needs Docker and `npx`; nothing else, and no
hosted project.

**Why this exists as a script rather than a paragraph in a runbook.** The
authorisation guarantee is the strongest claim this project makes, and it was
unverified for most of the build because verifying it meant creating an account,
copying four values, and exporting them by hand. That is enough friction to keep
a check un-run indefinitely. The first time it did run it found the migration
granting no table privileges at all -- correct policies sitting on a table no
role could reach.

The local stack's keys are the fixed development values Supabase publishes and
prints on `supabase start`. They are not secrets and grant access to nothing
outside this machine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

from biovision.config import BACKEND_ROOT

INFRA = BACKEND_ROOT.parent / "infra"
API = "http://127.0.0.1:54321"

USERS = (
    ("rls-a@example.com", "correct-horse-battery-staple-A1", "BIOVISION_TEST_USER_A_TOKEN"),
    ("rls-b@example.com", "correct-horse-battery-staple-B2", "BIOVISION_TEST_USER_B_TOKEN"),
)


def _npx(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npx", "--yes", "supabase@latest", *args],
        cwd=INFRA,
        text=True,
        capture_output=capture,
        shell=sys.platform == "win32",
        check=False,
    )


def stack_status() -> dict[str, str] | None:
    """Return the stack's connection details, or None if it is not up."""
    result = _npx("status", capture=True)
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and "ANON_KEY" in line:
            try:
                return dict(json.loads(line))
            except json.JSONDecodeError:
                return None
    return None


def token_for(email: str, password: str, anon_key: str) -> str:
    """Sign the user up, or sign them in if they already exist."""
    headers = {"apikey": anon_key, "content-type": "application/json"}
    payload = {"email": email, "password": password}

    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{API}/auth/v1/signup", headers=headers, json=payload)
        if response.status_code >= 400:
            response = client.post(
                f"{API}/auth/v1/token?grant_type=password", headers=headers, json=payload
            )
        response.raise_for_status()
        token = response.json().get("access_token")

    if not token:
        raise RuntimeError(f"no access_token returned for {email}")
    return str(token)


def main() -> int:
    if not (INFRA / "supabase" / "config.toml").is_file():
        print(f"no Supabase config at {INFRA / 'supabase'}; run `npx supabase init` there")
        return 1

    status = stack_status()
    if status is None:
        print("starting the local Supabase stack (first run downloads several images) ...")
        _npx("start")
        status = stack_status()

    if status is None:
        print("could not read `supabase status`; is Docker running?")
        return 1

    anon_key = status.get("ANON_KEY", "")
    if not anon_key:
        print("`supabase status` returned no ANON_KEY")
        return 1

    print(f"stack up at {status.get('API_URL', API)}")

    environment = dict(os.environ)
    environment["BIOVISION_TEST_SUPABASE"] = "1"
    environment["SUPABASE_URL"] = status.get("API_URL", API)
    environment["SUPABASE_ANON_KEY"] = anon_key

    for email, password, variable in USERS:
        environment[variable] = token_for(email, password, anon_key)
        print(f"  token for {email}")

    print()
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration/test_rls_live.py", "-v"],
        cwd=Path(BACKEND_ROOT),
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
