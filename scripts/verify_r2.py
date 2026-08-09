#!/usr/bin/env python3
"""Prove the R2 credentials in .env actually work, before any test relies on them.

Read-mostly and non-destructive: it lists buckets, confirms the configured one is
reachable, then writes / reads / deletes exactly one object under a clearly
marked probe key inside the configured prefix.

    uv run python scripts/verify_r2.py

Never prints a secret. Diagnoses the two failures that actually happen rather
than surfacing boto3's opaque errors:

  InvalidArgument "length N, should be 32"
      An account API token (My Profile → API Tokens), not an R2 API token.
      They are different systems. The S3 pair comes from R2 → Manage R2 API
      Tokens.

  SignatureDoesNotMatch
      Usually the endpoint carries a bucket path. augment-it's .env stores
      `…r2.cloudflarestorage.com/lossless-core`; boto3 wants the bare host.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
PROBE_KEY = "_corpora-builder-connectivity-probe.txt"


def load_env() -> dict[str, str]:
    if not ENV_PATH.is_file():
        print(f"No {ENV_PATH}", file=sys.stderr)
        raise SystemExit(1)
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def main() -> int:
    env = load_env()
    access = env.get("R2_ACCESS_KEY_ID", "")
    secret = env.get("R2_SECRET_ACCESS_KEY", "")
    endpoint = env.get("CLOUDFLARE_R2_API_ENDPOINT", "")
    bucket = env.get("CORPORA_R2_BUCKET", "")
    prefix = env.get("CORPORA_R2_PREFIX", "")

    print("config (values withheld):")
    print(f"  access key      {len(access)} chars, hex={bool(re.fullmatch('[0-9a-f]+', access))}")
    print(f"  secret          {len(secret)} chars, hex={bool(re.fullmatch('[0-9a-f]+', secret))}")
    print(f"  endpoint        {re.sub(r'//[a-f0-9]+', '//<ACCOUNT>', endpoint)}")
    print(f"  bucket/prefix   {bucket} / {prefix or '(none)'}")

    if not (access and secret and endpoint and bucket):
        print("\nMissing one of the four. Run scripts/import_r2_credentials.py.", file=sys.stderr)
        return 1
    if "/" in endpoint.split("://", 1)[-1]:
        print("\nEndpoint has a path after the host — boto3 needs the bare host.", file=sys.stderr)
        return 1

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="auto",
    )

    try:
        names = [b["Name"] for b in client.list_buckets()["Buckets"]]
        print(f"\n✓ authenticated — {len(names)} bucket(s): {', '.join(sorted(names))}")
        if bucket not in names:
            print(f"\n✗ '{bucket}' is not among them.", file=sys.stderr)
            return 1

        key = f"{prefix}{PROBE_KEY}"
        client.put_object(Bucket=bucket, Key=key, Body=b"corpora-builder probe\n")
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        assert body == b"corpora-builder probe\n"
        client.delete_object(Bucket=bucket, Key=key)
        print(f"✓ write/read/delete round-trip at {bucket}/{key}")

        existing = client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("KeyCount", 0)
        print(f"✓ {existing} object(s) already under prefix '{prefix or '(root)'}'")
        print("\nReady. Run the live conformance suite with CORPORA_R2_LIVE=1.")
        return 0

    except NoCredentialsError:
        print("\n✗ boto3 found no credentials.", file=sys.stderr)
        return 1
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"].get("Message", "")
        print(f"\n✗ {code}: {msg}", file=sys.stderr)
        if "should be 32" in msg or code == "InvalidArgument":
            print(
                "\n  That is an ACCOUNT API token, not an R2 API token.\n"
                "  Cloudflare has two separate systems and they look alike:\n"
                "    My Profile → API Tokens        → Cloudflare REST API. Not this.\n"
                "    R2 → Manage R2 API Tokens      → the S3 pair you need.\n"
                "  The S3 pair is 32 hex chars + 64 hex chars, shown ONCE at creation.",
                file=sys.stderr,
            )
        elif code == "SignatureDoesNotMatch":
            print("\n  Check the endpoint is the bare host, with no bucket path.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
