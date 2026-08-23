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
        display_name=env.get("CORPORA_WORKSPACE_NAME", ""),
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


def cmd_fetch(args: argparse.Namespace) -> int:
    """`corpora fetch` — bring a binary back from `bin/` to a local path.

    The door that makes removing binaries from a repo safe. Without it, "the
    bytes are in R2" is true and useless. See
    `context-v/specs/Binary-Ingest-And-Bin-Store.md` Behaviour 8 — absent is a
    state with an affordance, not an error.
    """
    import re

    from src.binary.store import BinStore

    store, _ = build_store(load_env(), args.local)
    binst = BinStore(store)

    key = args.key
    if not key.startswith("bin/"):
        # A wrapper path was given instead of a key — read the pointer off it.
        try:
            text = Path(key).read_text(errors="replace")
        except OSError:
            console.print(f"[red]not a bin/ key and not a readable file:[/] {key}")
            return 1
        m = re.search(r"binary_key:\s*(\S+)", text)
        if not m:
            console.print(f"[red]no binary_key in[/] {key}")
            return 1
        key = m.group(1)

    dest = Path(args.out) if args.out else Path(key.rsplit("/", 1)[-1])
    try:
        data = binst.remote.read(key)
    except Exception as err:  # noqa: BLE001 — the message is the product here
        console.print(f"[red]could not fetch[/] {key}: {err}")
        return 1
    dest.write_bytes(data)
    console.print(f"[green]{len(data):,} bytes[/] -> {dest}")
    return 0


def cmd_changes(args: argparse.Namespace) -> int:
    """`corpora changes` — what changed in a corpus, and why.

    Reads a `ChangeSource` rather than git directly, so the engine behind this
    can be swapped without touching the surface. See
    `context-v/specs/Corpus-Change-Feed.md`.
    """
    from src.feed.git_source import GitChangeSource, GitRepoError
    from src.feed.render import render_prose, to_json

    try:
        source = GitChangeSource(args.repo)
    except GitRepoError as err:
        console.print(f"[red]{err}[/]")
        return 1

    page = source.changes(prefix=args.prefix, limit=args.limit)

    if args.json:
        print(to_json(page))
    else:
        # Printed raw, not through rich: the renderer already returns finished
        # plain text, and rich soft-wraps long corpus paths mid-token.
        print(render_prose(page, max_paths=args.max_paths))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store, _ = build_store(load_env(), args.local)
    try:
        console.print(store.read(args.path).decode("utf-8", errors="replace"))
    except KeyNotFound:
        console.print(f"[red]not found:[/] {args.path}")
        return 1
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    """`corpora reindex` — rebuild the manifest, and the search bundle from it.

    The one operation that reads every source. Deliberately a command rather
    than something a page load can trigger: see `src/index/rebuild.py`.
    """
    from src.index.rebuild import reindex

    store, workspace = build_store(load_env(), args.local)

    with console.status("reading the corpus"):
        result = reindex(store, prefix=args.prefix, search=not args.no_search)

    console.print(f"[green]indexed[/] {result.sources} source(s) · {workspace.display_name}")
    console.print(f"  manifest    {result.fingerprint[:12]}")

    search = result.search
    if search.skipped:
        console.print(f"[dim]  search      skipped — {search.skipped}[/]")
    elif not search.ok:
        console.print(f"[red]  search      failed — {search.error}[/]")
        return 1
    else:
        console.print(
            f"  search      {search.records} record(s) in {search.files} file(s) "
            f"· {search.written} sent"
        )
    return 0


def cmd_backfill_urls(args: argparse.Namespace) -> int:
    """`corpora backfill-urls` — give every source a stable identity.

    **Dry run unless `--apply`.** It rewrites files in a corpus that may belong
    to a client, and the value of the operation is entirely in it being boring:
    a one-line insertion under `url:`, nothing else touched.
    """
    from src.model.backfill import apply as apply_backfill
    from src.model.backfill import plan as plan_backfill
    from src.server.browse import source_keys

    store, workspace = build_store(load_env(), args.local)

    with console.status("reading the corpus"):
        keys = source_keys(store, args.prefix)
        result = plan_backfill(store, keys)

    console.print(f"[green]{workspace.display_name}[/] · {len(keys)} source(s)")
    console.print(f"  would write   {len(result.writes)}")
    for reason, count in sorted(result.reasons().items(), key=lambda kv: -kv[1]):
        console.print(f"  [dim]skipped[/]       {count:>4}  {reason}")

    if not args.apply:
        console.print("\n[dim]Dry run. Re-run with --apply to write.[/]")
        for entry in result.writes[: args.sample]:
            console.print(f"  [dim]{entry.key}[/]")
            console.print(f"    -> normalized_url: {entry.normalized}")
        return 0

    if not result.writes:
        console.print("\n[dim]Nothing to do.[/]")
        return 0

    with console.status(f"writing {len(result.writes)} file(s)"):
        changed = apply_backfill(store, result)
    console.print(f"\n[green]wrote[/] {changed} file(s)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from src.server.app import create_app

    store, workspace = build_store(load_env(), args.local)
    label = args.local or workspace.display_name

    console.print(f"[green]corpora[/] · {label}")
    console.print(f"  [bold]http://{args.host}:{args.port}[/]\n")
    if args.writable:
        console.print("[yellow]  WRITABLE — capture is enabled against this target[/]\n")
    else:
        console.print("[dim]  read-only — pass --writable to enable capture[/]\n")

    uvicorn.run(
        create_app(store, label, writable=args.writable, workspace=workspace),
        host=args.host,
        port=args.port,
        log_level="warning",
    )
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

    serve = sub.add_parser("serve", help="open the browse UI")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument(
        "--writable",
        action="store_true",
        help="enable capture from the UI (off by default — the first target was a client corpus)",
    )
    serve.set_defaults(func=cmd_serve)

    fetch = sub.add_parser("fetch", help="bring a binary back from bin/")
    fetch.add_argument("key", help="a bin/ key, or the path of a wrapper .md that names one")
    fetch.add_argument("--out", help="where to write it (default: the key's filename)")
    fetch.add_argument("--local", default="", help="use a local corpus dir instead of R2")
    fetch.set_defaults(func=cmd_fetch)

    changes = sub.add_parser("changes", help="what changed in the corpus, and why")
    changes.add_argument("--repo", default=".", help="git repository holding the corpus")
    changes.add_argument("--prefix", default="", help="corpus path within the repo")
    changes.add_argument("--limit", type=int, default=10)
    changes.add_argument("--max-paths", type=int, default=5, dest="max_paths")
    changes.add_argument("--json", action="store_true", help="machine shape instead of prose")
    changes.set_defaults(func=cmd_changes)

    reindex_cmd = sub.add_parser("reindex", help="rebuild the search index")
    reindex_cmd.add_argument("--prefix", default="", help="limit to a subtree")
    reindex_cmd.add_argument(
        "--no-search",
        action="store_true",
        help="write the manifest only, skipping the Pagefind bundle",
    )
    reindex_cmd.set_defaults(func=cmd_reindex)

    backfill = sub.add_parser("backfill-urls", help="add normalized_url where it is missing")
    backfill.add_argument("--prefix", default="", help="limit to a subtree")
    backfill.add_argument(
        "--apply",
        action="store_true",
        help="actually write (default is a dry run — this edits a client corpus)",
    )
    backfill.add_argument("--sample", type=int, default=5, help="how many examples to print")
    backfill.set_defaults(func=cmd_backfill_urls)

    show = sub.add_parser("show", help="print one source file")
    show.add_argument("path")
    show.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
