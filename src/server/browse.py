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

from concurrent.futures import ThreadPoolExecutor, as_completed
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
    #: The `domains:` frontmatter list — `strategy:workforce-development` and
    #: friends. NOT the same thing as `domain` above: `domain` is the folder the
    #: bytes sit in, this is the emphasis the operator put on them. A source's
    #: folder says where it lives; this says which piece of work says "mainly
    #: look here" when you are drafting.
    domains: list[str] = field(default_factory=list)
    #: Set when the file could not be parsed. Present in the results regardless.
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class Listing:
    rows: list[SourceRow] = field(default_factory=list)
    total: int = 0
    domains: list[str] = field(default_factory=list)
    #: Everything in the corpus, before `focus` or `domain` narrowed it. Reported
    #: alongside `total` so a narrowed list can always say what it is a subset OF
    #: — "82 in Workforce Development · 832 in the corpus". A single number would
    #: make a filter look like the whole world.
    corpus_total: int = 0


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
    return asset.binary_key, state, asset.working_bytes, asset.was_compressed


def list_domains(store: CorpusStore, prefix: str = "") -> tuple[int, list[str]]:
    """`(count, domains)` from keys alone — no file body is read.

    What `/api/meta` needs to paint a window. Deriving it by reading all 845
    sources took **20.6 seconds** cold against R2 and is what the operator saw as
    a window stuck on "Starting the backend…". Both facts live in the key.
    """
    keys = [k for k in store.list(prefix) if k.endswith(".md")]
    return len(keys), sorted({_domain_of(k) for k in keys})


def _newest_first(keys: list[str]) -> list[str]:
    """Ordered by the filename's date prefix, newest first.

    Sorted by the filename rather than `fetched_at` because `fetched_at` is
    inside the file and the whole point is not to open it. The naming convention
    writes that prefix *from* `fetched_at`, so the orders agree; a file predating
    the convention sorts by name, which is an honest fallback rather than a
    confidently wrong date.
    """
    return sorted(keys, key=lambda k: k.rsplit("/", 1)[-1], reverse=True)


def _page_keys(keys: list[str], offset: int, limit: int) -> list[str]:
    """The window of keys to actually read, newest first.

    Sorted by the filename's date prefix rather than `fetched_at`, because
    `fetched_at` is inside the file and the whole point is not to open it. The
    naming convention writes that prefix *from* `fetched_at`, so the orders
    agree; a file predating the convention sorts by name, which is the honest
    fallback rather than a wrong date.
    """
    return _newest_first(keys)[offset : offset + limit]


#: Files that describe the corpus rather than being captured material.
#: An `index.md` is a domain's statement of the case; `AGENTS.md` and `README.md`
#: are instructions. Listing them as sources renders them with no URL and
#: `status: candidate`, indistinguishable from something we found and never
#: fetched — 13 such rows in reach-edu, inflating "845 sources" by that much.
NOT_SOURCES = ("index.md", "AGENTS.md", "README.md")

DOMAIN_INDEX = "index.md"


@dataclass
class DomainDef:
    """A domain's own declaration of what it is.

    Read from the `index.md` sitting in the folder, which carries `type`, `slug`
    and `title`. **This is the only join between a `domains:` tag and a folder,
    and it has to be**: the type vocabulary is open — reach-edu uses `strategy`
    and `topic`, another client uses `thesis` — and no rule maps a tag to a
    folder across it. `strategy`/`strategies` would tempt a `+s`; `thesis`/
    `theses` breaks it immediately, and the next client breaks whatever replaces
    that. The corpus already states the answer, so it is read rather than guessed.

    Nesting comes free for the same reason: the folder is wherever the `index.md`
    is, at any depth.
    """

    folder: str
    type: str
    slug: str
    title: str
    path: str

    @property
    def value(self) -> str:
        """The `domains:` tag this folder answers to."""
        return f"{self.type}:{self.slug}"

    def to_json(self) -> dict:
        return {
            "value": self.value,
            "label": self.title or self.slug,
            "type": self.type,
            "folder": self.folder,
            "path": self.path,
        }


def list_domain_defs(store: CorpusStore, prefix: str = "") -> list[DomainDef]:
    """Every domain that declares itself, by reading its `index.md`.

    One read per definition — nine in reach-edu — rather than one per source.
    A corpus with no `index.md` anywhere returns nothing, and the surfaces that
    depend on this simply do not appear, which is the honest outcome.
    """
    keys = [k for k in store.list(prefix) if k.rsplit("/", 1)[-1] == DOMAIN_INDEX]
    defs: list[DomainDef] = []
    if not keys:
        return defs

    blobs: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=min(16, len(keys))) as pool:
        futures = {pool.submit(store.read, k): k for k in keys}
        for fut in as_completed(futures):
            try:
                blobs[futures[fut]] = fut.result()
            except Exception:  # noqa: BLE001 - a missing definition is not fatal
                continue

    for key, blob in blobs.items():
        try:
            src = SourceFile.parse(blob.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        kind = str(src.unknown.get("type", "") or "")
        slug = str(src.unknown.get("slug", "") or "")
        if not kind or not slug:
            continue
        defs.append(
            DomainDef(
                folder=_domain_of(key),
                type=kind,
                slug=slug,
                title=src.title,
                path=key,
            )
        )
    return sorted(defs, key=lambda d: (d.type, d.title.lower() or d.slug))


def focus_folder(focus: str, defs: list[DomainDef]) -> str:
    """The folder a `type:slug` names, per the corpus's own declarations."""
    for d in defs:
        if d.value == focus:
            return d.folder
    return ""


def _in_domain(key: str, domain: str) -> bool:
    """Does `key` belong to `domain`, or to something nested under it?

    Filtering by *domain* rather than by raw key prefix is what keeps the client
    out of the storage layout. `_domain_of` already strips a leading `live/` and
    a trailing `sources/`, so the domain `topics/future-of-work` covers both
    `topics/future-of-work/x.md` and `live/topics/future-of-work/sources/x.md`.
    The browser previously sent `<domain>/` as a key prefix, which matched the
    first layout and silently returned nothing for the second.
    """
    d = _domain_of(key)
    return d == domain or d.startswith(domain + "/")


def list_sources(
    store: CorpusStore,
    prefix: str = "",
    search: str = "",
    limit: int = 200,
    offset: int = 0,
    bin_store: BinStore | None = None,
    domain: str = "",
    focus: str = "",
) -> Listing:
    """Every source under `prefix`, `domain` and `focus`, newest first.

    `focus` NARROWS. An earlier version had it merely reorder — everything
    returned, emphasised first — on the reading that "mainly look here" meant
    emphasis rather than membership. Driven in a real browser that is
    indistinguishable from nothing happening: with 200 rows on screen and 82
    matches, only the top of the list moves and rows 83-200 are unrelated.

    Access to the rest of the corpus is preserved by the toggle being a toggle —
    one click away — and by `corpus_total` riding alongside `total`, so a
    narrowed list always says what it is a subset of.
    """
    all_keys = [
        k
        for k in store.list(prefix)
        if k.endswith(".md") and k.rsplit("/", 1)[-1] not in NOT_SOURCES
    ]
    if domain:
        all_keys = [k for k in all_keys if _in_domain(k, domain)]

    corpus_total = len(all_keys)
    defs = list_domain_defs(store, prefix) if focus else []
    focus_dir = ""
    if focus:
        focus_dir = focus_folder(focus, defs)
        # Narrowed on the KEY, so a plain page load costs no extra reads. Exact
        # today: all 241 tagged sources sit in the folder their tag names and
        # none carries a second tag.
        #
        # A search is different — it opens every file anyway, so it CAN see a
        # tag on a source living outside the folder. There the narrowing happens
        # on rows instead, below, and is strictly more correct. The remaining
        # gap is a plain page load with no search, and the fix for that is an
        # index rather than 845 reads. See `context-v/specs/Strategy-Focus.md`.
        if not search:
            all_keys = [k for k in all_keys if _in_domain(k, focus_dir)]
    domains = {_domain_of(k) for k in all_keys}

    # A search has to look at everything. A page load does not, and pretending
    # otherwise costs 845 network reads to show 50 rows.
    total = len(all_keys)
    paged = not search
    keys = _page_keys(all_keys, offset, limit) if paged else all_keys

    rows: list[SourceRow] = []

    # Read the page concurrently. Against R2 each GET is ~140ms of latency and
    # almost no transfer, so fifty sequential reads spend seven seconds waiting
    # rather than working. botocore clients are thread-safe for requests, and a
    # LocalFsStore does not care. Order is restored below.
    blobs: dict[str, bytes | Exception] = {}
    if keys:
        with ThreadPoolExecutor(max_workers=min(16, len(keys))) as pool:
            futures = {pool.submit(store.read, k): k for k in keys}
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    blobs[key] = fut.result()
                except Exception as exc:  # noqa: BLE001 - recorded, not raised
                    blobs[key] = exc

    for key in keys:
        domain = _domain_of(key)
        try:
            blob = blobs[key]
            if isinstance(blob, Exception):
                raise blob
            source = SourceFile.parse(blob.decode("utf-8", errors="replace"))
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
                domains=list(source.domains),
            )
        )

    if search:
        needle = search.lower()
        rows = [
            r
            for r in rows
            if needle in r.title.lower() or needle in r.excerpt.lower() or needle in r.path.lower()
            # The `domains:` tag is searchable text too. Typing "literacy" should
            # reach a source that carries `strategy:adult-literacy-numeracy` even
            # when neither its title nor its excerpt says the word.
            or any(needle in d.lower() for d in r.domains)
        ]

    if search and focus:
        # Every file was opened for the search, so the tag is visible here even
        # on a source living outside the focus's folder — a strictly better
        # narrowing than the key-level one, and free at this point.
        rows = [r for r in rows if _in_domain(r.path, focus_dir) or focus in r.domains]
        total = len(rows)

    if paged:
        # Already ordered and windowed by key; re-slicing would drop rows.
        return Listing(rows=rows, total=total, domains=sorted(domains), corpus_total=corpus_total)

    # Newest fetch first — the question a corpus browser answers most often is
    # "what did I just add". Damaged rows have no fetched_at and sort last.
    rows.sort(key=lambda r: r.fetched_at, reverse=True)
    return Listing(
        rows=rows[offset : offset + limit],
        total=len(rows),
        domains=sorted(domains),
        corpus_total=corpus_total,
    )


def load_source(store: CorpusStore, path: str) -> str:
    """One source's raw text, unmodified.

    Refuses traversal. The surface is localhost-only and read-only, but a path
    parameter that reaches outside the corpus is a hole regardless of who is
    listening.
    """
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"path outside the corpus: {path!r}")
    return store.read(path).decode("utf-8", errors="replace")
