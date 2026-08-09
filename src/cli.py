"""`corpora` — the command line.

    corpora add <url> [--domain thesis/ocean-energy] [--fetch]
    corpora ls [prefix]
    corpora show <path>

Configuration comes from `.env` in the repo root: R2 credentials, and the one
variable that names the workspace. Storage is resolved from the workspace rather
than assembled here, so nothing in this file names a bucket — which is what lets
a didi.sh login replace the config later without touching a call site.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.capture import JinaFetcher, add_source
from src.identity import StaticWorkspaceResolver, Workspace
from src.model import SourceFile
from src.store import CachedStore, CorpusStore, KeyNotFound, LocalFsStore, R2Store

console = Console()
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if match:
            env[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    return env


def build_store(env: dict[str, str], local: str = "") -> tuple[CorpusStore, Workspace]:
    """The store and the workspace it belongs to.

    `--local` swaps the substrate for a directory without changing anything
    above it. That is the storage seam doing its job, and it is also how you
    try the tool without touching a client bucket.
    """
    workspace = StaticWorkspaceResolver(
        slug=env.get("CORPORA_WORKSPACE", "local"),
        display_name=env.get("CORPORA_WORKSPACE_NAME", env.get("CORPORA_WORKSPACE", "local")),
        bucket=env.get("CORPORA_R2_BUCKET") or None,
        prefix=env.get("CORPORA_R2_PREFIX", ""),
    ).resolve()

    if local:
        return LocalFsStore(Path(local)), workspace

    import boto3

    missing = [
        k
        for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_API_ENDPOINT")
        if not env.get(k)
    ]
    if missing:
        console.print(f"[red]Missing in .env:[/] {', '.join(missing)}")
        console.print("Run [bold]scripts/import_r2_credentials.py[/], or pass --local <dir>.")
        raise SystemExit(1)

    client = boto3.client(
        "s3",
        endpoint_url=env["CLOUDFLARE_R2_API_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    return (
        CachedStore(R2Store(bucket=workspace.bucket, client=client, prefix=workspace.prefix)),
        workspace,
    )


def cmd_add(args: argparse.Namespace) -> int:
    store, workspace = build_store(load_env(), args.local)

    with console.status(f"fetching {args.url}"):
        result = add_source(
            store,
            args.url,
            JinaFetcher(),
            domain=args.domain,
            full=args.fetch,
            origin=args.origin,
        )

    if not result.created:
        console.print(f"[yellow]already in the corpus[/] → {result.duplicate_of}")
        return 0

    source = result.source
    console.print(f"[green]added[/] → {result.path}")
    console.print(f"  workspace   {workspace.display_name} ({workspace.bucket})")
    console.print(f"  title       {source.title or '[dim](none)[/]'}")
    console.print(f"  published   {source.published_at or '[dim](unknown)[/]'}")
    console.print(f"  status      {source.status} · content_pulled={source.content_pulled}")
    console.print(f"  machine     {source.machine_verdict}")
    if source.binary_asset:
        console.print(
            f"  binary      {source.binary_asset.filename} "
            f"({source.binary_asset.download_status})"
        )
    if not args.fetch:
        console.print("[dim]  metadata only — re-run with --fetch to pull the body[/]")
    return 0


def cmd_ls(args: argparse.Namespace) -> int:
    store, workspace = build_store(load_env(), args.local)
    keys = [k for k in store.list(args.prefix) if k.endswith(".md")]

    if not keys:
        console.print(f"[dim]nothing under {args.prefix or '(root)'}[/]")
        return 0

    table = Table(title=f"{workspace.display_name} — {len(keys)} source(s)")
    table.add_column("status", style="cyan")
    table.add_column("pulled")
    table.add_column("title")
    table.add_column("path", style="dim")

    for key in keys[: args.limit]:
        try:
            source = SourceFile.parse(store.read(key).decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 - a damaged file must still list
            table.add_row("[red]ERROR[/]", "", f"[red]{type(exc).__name__}[/]", key)
            continue
        table.add_row(
            source.status,
            "yes" if source.content_pulled else "no",
            (source.title or "")[:60],
            key,
        )

    console.print(table)
    if len(keys) > args.limit:
        console.print(f"[dim]… {len(keys) - args.limit} more; raise --limit[/]")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store, _ = build_store(load_env(), args.local)
    try:
        console.print(store.read(args.path).decode("utf-8", errors="replace"))
    except KeyNotFound:
        console.print(f"[red]not found:[/] {args.path}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corpora", description="Build corpora deliberately.")
    parser.add_argument("--local", default="", help="use a local directory instead of R2")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="capture a URL into the corpus")
    add.add_argument("url")
    add.add_argument("--domain", default=None, help="<type>/<slug>; omit to file in the inbox")
    add.add_argument(
        "--fetch",
        action="store_true",
        help="pull the full body (default is metadata only — gate the enrichment)",
    )
    add.add_argument("--origin", default="analyst-paste")
    add.set_defaults(func=cmd_add)

    ls = sub.add_parser("ls", help="list sources")
    ls.add_argument("prefix", nargs="?", default="live/")
    ls.add_argument("--limit", type=int, default=50)
    ls.set_defaults(func=cmd_ls)

    show = sub.add_parser("show", help="print one source file")
    show.add_argument("path")
    show.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
