#!/usr/bin/env python3
"""Pull R2 S3 credentials out of whatever Cloudflare handed you, into .env.

Cloudflare presents R2 credentials in several shapes depending on where you are
in the dashboard and how recently the UI changed — a JSON blob, a downloaded
file, a rclone-style config snippet, or two labelled fields. This accepts all of
them and never prints a secret.

Usage
-----
    # from a downloaded / pasted JSON file
    uv run python scripts/import_r2_credentials.py ~/Downloads/r2-token.json

    # or paste the two values interactively (input is not echoed)
    uv run python scripts/import_r2_credentials.py

What it looks for, case- and separator-insensitively:

    access key id      accessKeyId, access_key_id, AWS_ACCESS_KEY_ID, id
    secret access key  secretAccessKey, secret_access_key, AWS_SECRET_ACCESS_KEY
    endpoint           endpoint, endpointS3, CLOUDFLARE_R2_API_ENDPOINT

A note on which token you need: Cloudflare's **account** API tokens (My Profile →
API Tokens) are NOT S3 credentials — they drive the Cloudflare REST API. The S3
pair comes from **R2 → Manage R2 API Tokens**. If what you have is a single
long opaque token string with no access-key/secret pair, it is the former.
"""

from __future__ import annotations

import getpass
import json
import re
import sys
from pathlib import Path
from typing import Any

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_ACCESS_HINTS = ("accesskeyid", "awsaccesskeyid", "accesskey")
_SECRET_HINTS = ("secretaccesskey", "awssecretaccesskey", "secretkey")
_ENDPOINT_HINTS = ("endpoints3", "endpoint", "r2apiendpoint", "s3api")


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _walk(obj: Any) -> dict[str, str]:
    """Flatten nested JSON to normalised-key -> string-value."""
    flat: dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                flat.update(_walk(v))
            elif v is not None:
                flat[_norm(str(k))] = str(v)
    elif isinstance(obj, list):
        for item in obj:
            flat.update(_walk(item))
    return flat


def _pick(flat: dict[str, str], hints: tuple[str, ...]) -> str:
    for hint in hints:
        for key, value in flat.items():
            if key == hint and value:
                return value
    for hint in hints:
        for key, value in flat.items():
            if hint in key and value:
                return value
    return ""


def _from_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    try:
        return _walk(json.loads(text))
    except json.JSONDecodeError:
        # Not JSON — try `key = value` / `key: value` lines (rclone, .env, or a
        # copied dashboard block).
        flat: dict[str, str] = {}
        for line in text.splitlines():
            m = re.match(r'^\s*"?([A-Za-z0-9_\- ]+)"?\s*[:=]\s*"?([^"\s,]+)"?', line)
            if m:
                flat[_norm(m.group(1))] = m.group(2)
        return flat


def _update_env(access: str, secret: str, endpoint: str) -> list[str]:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    updates = {
        "R2_ACCESS_KEY_ID": access,
        "R2_SECRET_ACCESS_KEY": secret,
    }
    if endpoint:
        host = re.match(r"(https://[^/]+)", endpoint)
        updates["CLOUDFLARE_R2_API_ENDPOINT"] = host.group(1) if host else endpoint

    changed = []
    for name, value in updates.items():
        if not value:
            continue
        for i, line in enumerate(lines):
            if line.startswith(f"{name}="):
                lines[i] = f"{name}={value}"
                break
        else:
            lines.append(f"{name}={value}")
        changed.append(name)

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser()
        if not path.is_file():
            print(f"No such file: {path}", file=sys.stderr)
            return 1
        flat = _from_file(path)
        access = _pick(flat, _ACCESS_HINTS)
        secret = _pick(flat, _SECRET_HINTS)
        endpoint = _pick(flat, _ENDPOINT_HINTS)
        if not (access and secret):
            print(
                "Could not find an access-key/secret pair in that file.\n"
                f"Keys it did contain: {sorted(flat)[:20]}\n\n"
                "If none of those look like an S3 credential pair, this is probably\n"
                "an account API token rather than an R2 API token. The S3 pair comes\n"
                "from R2 → Manage R2 API Tokens.",
                file=sys.stderr,
            )
            return 1
    else:
        print("Paste the two values from R2 → Manage R2 API Tokens (input hidden).\n")
        access = getpass.getpass("Access Key ID:     ").strip()
        secret = getpass.getpass("Secret Access Key: ").strip()
        endpoint = ""

    # Shape check before we write anything — R2 access keys are 32 hex chars and
    # secrets are 64. Catching a placeholder or a wrong-token paste here is much
    # cheaper than catching it as an opaque InvalidArgument from the API.
    warnings = []
    if not re.fullmatch(r"[0-9a-f]{32}", access):
        warnings.append(f"  access key is {len(access)} chars, expected 32 hex")
    if not re.fullmatch(r"[0-9a-f]{64}", secret):
        warnings.append(f"  secret is {len(secret)} chars, expected 64 hex")
    if warnings:
        print("These do not look like R2 S3 credentials:", file=sys.stderr)
        print("\n".join(warnings), file=sys.stderr)
        print(
            "\nWriting anyway — but if the next call fails with InvalidArgument,\n"
            "this is why. Account API tokens will not work here.",
            file=sys.stderr,
        )

    changed = _update_env(access, secret, endpoint)
    print(f"\nUpdated {ENV_PATH.name}: {', '.join(changed)}")
    print("Values were never printed. Run scripts/verify_r2.py next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
