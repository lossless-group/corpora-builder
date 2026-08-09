"""The FastAPI surface — read-only, localhost, one page.

Deliberately thin. Every decision about what the screen shows lives in
`browse.py`, where it is tested without a running server.

**No handler writes.** Not a policy to remember, a property to check: nothing
here calls `store.write` or `store.delete`. That is what lets this ship against
a real client corpus before the triage-and-rewrite questions are settled.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from src.server.browse import list_sources, load_source
from src.store import CorpusStore, KeyNotFound

STATIC = Path(__file__).parent / "static"


def create_app(store: CorpusStore, label: str = "corpus") -> FastAPI:
    app = FastAPI(title="corpora-builder", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/meta")
    def meta() -> dict[str, object]:
        listing = list_sources(store, limit=0)
        return {"label": label, "total": listing.total, "domains": listing.domains}

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

    return app
