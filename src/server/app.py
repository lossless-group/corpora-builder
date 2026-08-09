"""The FastAPI surface — read-only, localhost, one page.

Deliberately thin. Every decision about what the screen shows lives in
`browse.py`, where it is tested without a running server.

**No handler writes.** Not a policy to remember, a property to check: nothing
here calls `store.write` or `store.delete`. That is what lets this ship against
a real client corpus before the triage-and-rewrite questions are settled.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from src.capture import JinaFetcher, add_source
from src.server.browse import list_sources, load_source
from src.store import CorpusStore, KeyNotFound

STATIC = Path(__file__).parent / "static"


def create_app(store: CorpusStore, label: str = "corpus", writable: bool = False) -> FastAPI:
    """The sidecar.

    `writable` is a SERVER-level decision, not a per-request one. The first
    thing this surface was ever pointed at was a client corpus on the
    Autonomy-Gates RED list; read-only made that safe, and a browse tool that
    silently gained the ability to write into one is the accident worth
    designing against. Gate the step that changes things, and make the gate
    something you pass through deliberately.
    """
    app = FastAPI(title="corpora-builder", docs_url=None, redoc_url=None)

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
        listing = list_sources(store, limit=0)
        return {
            "label": label,
            "total": listing.total,
            "domains": listing.domains,
            "writable": writable,
        }

    @app.get("/api/sources")
    def sources(
        prefix: str = Query(""),
        search: str = Query(""),
        limit: int = Query(200, ge=1, le=2000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        listing = list_sources(store, prefix=prefix, search=search, limit=limit, offset=offset)
        return {
            "rows": [r.as_dict() for r in listing.rows],
            "total": listing.total,
            "domains": listing.domains,
        }

    @app.get("/api/source", response_class=PlainTextResponse)
    def source(path: str = Query(...)) -> str:
        try:
            return load_source(store, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyNotFound as exc:
            raise HTTPException(status_code=404, detail=f"not found: {path}") from exc

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
