"""The FastAPI surface — read-only, localhost, one page.

Deliberately thin. Every decision about what the screen shows lives in
`browse.py`, where it is tested without a running server.

**No handler writes.** Not a policy to remember, a property to check: nothing
here calls `store.write` or `store.delete`. That is what lets this ship against
a real client corpus before the triage-and-rewrite questions are settled.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from src.binary.keys import BinaryRef
from src.binary.store import BinStore
from src.capture import JinaFetcher, add_source
from src.feed.git_source import GitChangeSource, GitRepoError
from src.feed.render import to_json
from src.server.browse import list_domain_defs, list_domains, list_sources, load_source
from src.server.tree import build_tree
from src.store import CorpusStore, KeyNotFound

STATIC = Path(__file__).parent / "static"


def create_app(
    store: CorpusStore,
    label: str = "corpus",
    writable: bool = False,
    bin_store: BinStore | None = None,
) -> FastAPI:
    """The sidecar.

    `writable` is a SERVER-level decision, not a per-request one. The first
    thing this surface was ever pointed at was a client corpus on the
    Autonomy-Gates RED list; read-only made that safe, and a browse tool that
    silently gained the ability to write into one is the accident worth
    designing against. Gate the step that changes things, and make the gate
    something you pass through deliberately.
    """
    app = FastAPI(title="corpora-builder", docs_url=None, redoc_url=None)

    # One per server. The cache is machine-level and shared across every corpus,
    # so this is a handle rather than state — see Binary-Ingest-And-Bin-Store.
    #
    # Injectable because the default is the REAL machine cache: a test that let
    # it default read whatever this laptop happened to have downloaded and
    # reported `present` for a binary it had just evicted. A false green of
    # exactly the kind this repo keeps finding.
    bins = bin_store or BinStore(store)

    # The Tauri webview talks to this sidecar directly over localhost rather
    # than through a Rust forwarding layer — which is what keeps the Rust side
    # to spawn/health-check/kill instead of memopop's ~800-line dispatcher. The
    # cost is that Tauri's origins are part of the CORS contract, and a new one
    # silently fails as a browser error rather than a server one.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        """What the Tauri SidecarManager probes before and after spawning."""
        return {"ok": True, "label": label, "writable": writable}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/meta")
    def meta() -> dict[str, object]:
        total, domains = list_domains(store)
        return {
            "label": label,
            "total": total,
            "domains": domains,
            # Read from each domain's own index.md — nine reads, not 845 —
            # because the type vocabulary is open and no rule maps a tag to a
            # folder across it. See DomainDef.
            "focuses": [d.to_json() for d in list_domain_defs(store)],
            "writable": writable,
        }

    @app.get("/api/tree")
    def tree() -> dict[str, object]:
        """The corpus as a folder tree — one `list()` call, zero file reads.

        Every key, not just the `.md` wrappers: `bin/` is part of the corpus and
        a client asking where their PDFs went deserves to see them.
        """
        keys = store.list("")
        return {"total": len(keys), "tree": [n.to_json() for n in build_tree(keys)]}

    @app.get("/api/sources")
    def sources(
        prefix: str = Query(""),
        domain: str = Query("", description="filter by domain folder, layout-independent"),
        focus: str = Query("", description="emphasise this `type:slug`; orders, never excludes"),
        search: str = Query(""),
        limit: int = Query(200, ge=1, le=2000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        listing = list_sources(
            store,
            prefix=prefix,
            domain=domain,
            focus=focus,
            search=search,
            limit=limit,
            offset=offset,
            bin_store=bins,
        )
        return {
            "rows": [r.as_dict() for r in listing.rows],
            "total": listing.total,
            "domains": listing.domains,
            "corpus_total": listing.corpus_total,
        }

    @app.get("/api/source", response_class=PlainTextResponse)
    def source(path: str = Query(...)) -> str:
        try:
            return load_source(store, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyNotFound as exc:
            raise HTTPException(status_code=404, detail=f"not found: {path}") from exc

    @app.get("/api/changes")
    def changes(
        repo: str = Query(..., description="git repository holding the corpus"),
        prefix: str = Query("", description="corpus path within that repo"),
        limit: int = Query(20, ge=1, le=200),
    ) -> dict[str, object]:
        """The change feed, as data. Same records `corpora changes` renders.

        Takes a repo path because history lives in git today and the sidecar
        serves a *store*, which may be a bucket with no history of its own. When
        the engine moves — Kopia, or our own checkpoints — this argument is what
        changes, and the response shape does not.
        """
        try:
            page = GitChangeSource(repo).changes(prefix=prefix, limit=limit)
        except GitRepoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return json.loads(to_json(page))

    @app.get("/api/binary")
    def binary(key: str = Query(..., description="a bin/ key")) -> Response:
        """Fetch a binary's bytes, populating the local cache.

        Allowed on a read-only server. This is the one read that writes, and it
        writes to a *cache* — populating it from an immutable content-addressed
        object cannot alter the corpus. Stated in Browse-Corpus Behaviour 12 so
        nobody later gates it behind `--writable`.
        """
        if not key.startswith("bin/") or ".." in key:
            raise HTTPException(status_code=400, detail="not a bin/ key")
        try:
            BinaryRef.from_key(key)  # the key must carry a sha256 to be one of ours
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            data = bins.fetch(BinaryRef.from_key(key))
        except KeyNotFound as exc:
            raise HTTPException(status_code=404, detail=f"not in the store: {key}") from exc
        return Response(
            content=data,
            media_type="application/pdf" if key.endswith(".pdf") else "application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{key.rsplit("/", 1)[-1]}"'},
        )

    @app.post("/api/capture")
    def capture(
        url: str = Body(..., embed=True),
        domain: str | None = Body(None, embed=True),
        full: bool = Body(False, embed=True),
    ) -> dict[str, object]:
        if not writable:
            raise HTTPException(
                status_code=403,
                detail="this server is read-only; restart with --writable to capture",
            )
        result = add_source(store, url, JinaFetcher(), domain=domain or None, full=full)
        source = result.source
        return {
            "path": result.path,
            "created": result.created,
            "duplicate_of": result.duplicate_of,
            "title": source.title,
            "status": source.status,
            "content_pulled": source.content_pulled,
            "machine_verdict": source.machine_verdict,
        }

    return app
