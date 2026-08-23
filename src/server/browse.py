"""Reading a corpus for display. Pure functions, no HTTP.

Kept apart from the FastAPI wiring so the behaviour is testable without a
server, following the same instinct as `src/ledger.py`: logic that can only be
exercised through a running process is logic nobody tests.

One rule matters more than the rest. **A file that will not parse appears in the
listing carrying its error.** The ImmuneCo failure was 13 sources being silently
absent from a count, and a browse screen that quietly drops what it cannot read
reproduces that exactly — with the added insult of looking tidy while doing it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from src.binary.store import BinStore
from src.capture.fetch import prose_excerpt
from src.model import SourceFile
from src.store import CorpusStore

#: How much body prose to show when a file carries no `excerpt`. Larger than the
#: capture-time cap because this is a reading surface, not a stored field.
PREVIEW_CHARS = 240


@dataclass
class SourceRow:
    """One row of the listing."""

    path: str
    domain: str
    title: str = ""
    status: str = ""
    content_pulled: bool = False
    published_at: str = ""
    fetched_at: str = ""
    excerpt: str = ""
    url: str = ""
    #: The content-addressed object this source's binary lives in, when it has
    #: one. Empty for text-only sources, which are most of them.
    binary_key: str = ""
    #: Whether those bytes are on THIS machine. `not_downloaded` is a state with
    #: an affordance, not an error — see Binary-Ingest-And-Bin-Store Behaviour 8.
    binary_state: str = ""
    binary_bytes: int = 0
    binary_optimized: bool = False
    #: Set when the file could not be parsed. Present in the results regardless.
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class Listing:
    rows: list[SourceRow] = field(default_factory=list)
    total: int = 0
    domains: list[str] = field(default_factory=list)


def _domain_of(path: str) -> str:
    """The folder a source belongs to, as an operator would name it.

    Handles both layouts in the wild. corpora-builder writes
    `live/<type>/<slug>/sources/<file>`; reach-edu's existing corpus, built
    before this tool, uses `funders/<slug>/<file>` and
    `strategies/<slug>/sources/<file>`. A trailing `sources` segment is
    plumbing, not a domain name, so it is dropped either way.
    """
    parts = path.split("/")[:-1]
    if parts and parts[0] == "live":
        parts = parts[1:]
    if parts and parts[-1] == "sources":
        parts = parts[:-1]
    return "/".join(parts) or "(root)"


def _binary_state(source: SourceFile, bin_store: BinStore | None) -> tuple[str, str, int, bool]:
    """`(key, state, bytes, optimized)` for a source's binary, if it has one.

    `state` is empty for text-only sources — most of them — and otherwise
    `present` or `not_downloaded`. Determining it costs a filesystem check
    against the local cache and never a network call, which is what lets a
    listing of 858 rows stay fast.
    """
    asset = source.binary_asset
    if asset is None or not asset.binary_key:
        return "", "", 0, False
    state = "present" if bin_store and bin_store.is_cached(asset.binary_key) else "not_downloaded"
    return asset.binary_key, state, asset.working_bytes, asset.optimized


def list_sources(
    store: CorpusStore,
    prefix: str = "",
    search: str = "",
    limit: int = 200,
    offset: int = 0,
    bin_store: BinStore | None = None,
) -> Listing:
    """Every source under `prefix`, newest fetch first."""
    keys = [k for k in store.list(prefix) if k.endswith(".md")]
    rows: list[SourceRow] = []
    domains: set[str] = set()

    for key in keys:
        domain = _domain_of(key)
        domains.add(domain)
        try:
            source = SourceFile.parse(store.read(key).decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 - a damaged file must still list
            rows.append(
                SourceRow(
                    path=key,
                    domain=domain,
                    title=key.rsplit("/", 1)[-1],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        bin_key, bin_state, bin_size, bin_opt = _binary_state(source, bin_store)
        rows.append(
            SourceRow(
                path=key,
                domain=domain,
                title=source.title,
                status=source.status,
                content_pulled=source.content_pulled,
                published_at=str(source.published_at or ""),
                fetched_at=str(source.fetched_at or ""),
                # Fall back to the body. reach-edu's 845 files carry no
                # `excerpt` at all — they predate the field — and a browse
                # screen of bare titles is not worth opening.
                excerpt=source.excerpt or prose_excerpt(source.body, PREVIEW_CHARS),
                url=source.url,
                binary_key=bin_key,
                binary_state=bin_state,
                binary_bytes=bin_size,
                binary_optimized=bin_opt,
            )
        )

    if search:
        needle = search.lower()
        rows = [
            r
            for r in rows
            if needle in r.title.lower() or needle in r.excerpt.lower() or needle in r.path.lower()
        ]

    # Newest fetch first — the question a corpus browser answers most often is
    # "what did I just add". Damaged rows have no fetched_at and sort last.
    rows.sort(key=lambda r: r.fetched_at, reverse=True)

    return Listing(rows=rows[offset : offset + limit], total=len(rows), domains=sorted(domains))


def load_source(store: CorpusStore, path: str) -> str:
    """One source's raw text, unmodified.

    Refuses traversal. The surface is localhost-only and read-only, but a path
    parameter that reaches outside the corpus is a hole regardless of who is
    listening.
    """
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"path outside the corpus: {path!r}")
    return store.read(path).decode("utf-8", errors="replace")
