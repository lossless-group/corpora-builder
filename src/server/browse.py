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
from src.index.manifest import (
    INDEX_PREFIX,
    MANIFEST_KEY,
    Entry,
    Manifest,
    entry_from_failure,
    entry_from_source,
    load_manifest,
)
from src.model import SourceFile
from src.model.domains import any_match
from src.store import CorpusStore


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
    #: friends. **Domain REFERENCES, not tags**: `tags:` is a separate field
    #: carrying Train-Case labels (`Workforce-Development`) and does not cascade.
    #: NOT the same thing as `domain` above either: `domain` is the folder the
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
    #: True when a manifest exists but the store holds keys it has never seen.
    #: Those keys are read individually so the listing is still correct — this
    #: flag says the index needs rebuilding, not that the answer is wrong. An
    #: edit in place is the case it CANNOT see; see Search-Index Behaviour 5.
    index_stale: bool = False


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


def focus_folders(focus: str, defs: list[DomainDef]) -> list[str]:
    """Every folder that falls under `focus`, per the corpus's own declarations.

    A LIST, because a domain reference cascades: focusing `strategy` names every
    declared strategy, not one. An exact lookup returned `""` for any chain that
    was not itself a declaration — and `_in_domain(key, "")` means *no
    narrowing*, so a focus nobody had declared silently matched the whole corpus.
    Found by `FOCUS-09`.

    Empty means no declared folder falls under this focus. That is a real answer:
    the reference on a row may still match, and if neither does, nothing does.
    """
    return [d.folder for d in defs if any_match([d.value], focus)]


def in_any_folder(key: str, folders: list[str]) -> bool:
    """Whether `key` sits under any of `folders`. Empty list is never a match."""
    return any(_in_domain(key, f) for f in folders)


def _in_domain(key: str, domain: str) -> bool:
    """Does `key` belong to `domain`, or to something nested under it?

    Filtering by *domain* rather than by raw key prefix is what keeps the client
    out of the storage layout. `_domain_of` already strips a leading `live/` and
    a trailing `sources/`, so the domain `topics/future-of-work` covers both
    `topics/future-of-work/x.md` and `live/topics/future-of-work/sources/x.md`.
    The browser previously sent `<domain>/` as a key prefix, which matched the
    first layout and silently returned nothing for the second.
    """
    # A trailing slash is a legal filter value, not a malformed one: the domain
    # combobox's segment-wise Backspace walks
    # `funders/ascendium-education` -> `funders/` -> `''`, and `funders/` is
    # exactly the "show me the whole parent" state that walk exists to produce.
    # Compared literally it matched nothing — `funders/` is never equal to a
    # domain and `funders//` is never a prefix of one — so every widened filter
    # silently returned zero rows. Found by driving the app, not by reading.
    domain = domain.rstrip("/")
    if not domain:
        return True
    d = _domain_of(key)
    return d == domain or d.startswith(domain + "/")


def row_from_entry(entry: Entry, bin_store: BinStore | None) -> SourceRow:
    """A listing row. **The only row builder there is.**

    Both paths reach it through an `Entry`: the indexed path reads one out of the
    manifest, the unindexed path parses a file into one and throws it away. That
    is deliberate. Two row builders — one for files, one for the index — would be
    two things to keep in step, and the way that failure presents is "search
    finds different things than the page." `INDEX-07` asserts the agreement;
    having a single function is what makes it true.

    `binary_state` is the one field recomputed rather than stored, because it is
    a fact about THIS machine and the manifest is shared. A cached copy of that
    answer would report `present` on a laptop that has never downloaded the
    bytes. It costs a filesystem check against the local cache and never a
    network call, which is what lets a listing of 858 rows stay fast.
    """
    state = ""
    if entry.binary_key:
        cached = bool(bin_store and bin_store.is_cached(entry.binary_key))
        state = "present" if cached else "not_downloaded"
    return SourceRow(
        path=entry.key,
        domain=_domain_of(entry.key),
        title=entry.title,
        status=entry.status,
        content_pulled=entry.content_pulled,
        published_at=entry.published_at,
        fetched_at=entry.fetched_at,
        excerpt=entry.excerpt,
        url=entry.url,
        binary_key=entry.binary_key,
        binary_state=state,
        binary_bytes=entry.binary_bytes,
        binary_optimized=entry.binary_optimized,
        domains=list(entry.domains),
        error=entry.error,
    )


def _read_many(store: CorpusStore, keys: list[str]) -> dict[str, bytes | Exception]:
    """Read `keys` concurrently, recording failures rather than raising.

    Against R2 each GET is ~140ms of latency and almost no transfer, so fifty
    sequential reads spend seven seconds waiting rather than working. botocore
    clients are thread-safe for requests, and a LocalFsStore does not care.
    """
    blobs: dict[str, bytes | Exception] = {}
    if not keys:
        return blobs
    with ThreadPoolExecutor(max_workers=min(16, len(keys))) as pool:
        futures = {pool.submit(store.read, k): k for k in keys}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                blobs[key] = fut.result()
            except Exception as exc:  # noqa: BLE001 - recorded, not raised
                blobs[key] = exc
    return blobs


def _entry_for(key: str, blob: bytes | Exception) -> Entry:
    """One key's manifest entry, whether or not it parsed."""
    try:
        if isinstance(blob, Exception):
            raise blob
        return entry_from_source(key, SourceFile.parse(blob.decode("utf-8", errors="replace")))
    except Exception as exc:  # noqa: BLE001 - a damaged file must still list
        return entry_from_failure(key, f"{type(exc).__name__}: {exc}")


def build_manifest(store: CorpusStore, prefix: str = "") -> Manifest:
    """Read the corpus once and write down what a listing needs.

    The expensive operation, run deliberately by `corpora reindex` — never as a
    side effect of browsing, which would put an 845-read rebuild behind an
    innocent page load.
    """
    keys = source_keys(store, prefix)
    blobs = _read_many(store, keys)
    return Manifest(entries={k: _entry_for(k, blobs.get(k, KeyError(k))) for k in keys})


def _source_keys(keys: list[str]) -> list[str]:
    """The captured sources among `keys`.

    Excludes the corpus's own documentation (`NOT_SOURCES`) and everything under
    `index/`, which this tool derives rather than captures.
    """
    return [
        k
        for k in keys
        if k.endswith(".md")
        and not k.startswith(INDEX_PREFIX)
        and k.rsplit("/", 1)[-1] not in NOT_SOURCES
    ]


def source_keys(store: CorpusStore, prefix: str = "") -> list[str]:
    """Every key under `prefix` that is a captured source."""
    return _source_keys(store.list(prefix))


def _is_indexed(store: CorpusStore, keys: list[str], prefix: str) -> bool:
    """Whether the corpus carries a manifest — without spending a request to ask.

    The key listing is already in hand, so an unindexed corpus costs nothing to
    detect. That matters: reading `index/sources.jsonl` speculatively would put a
    404 round-trip on every listing of every corpus that has never been indexed,
    and `BROWSE-15` measures exactly this in read counts.

    Only a *prefixed* listing has to ask, because a prefix that is not `index/`
    cannot see the manifest in its own results.
    """
    if MANIFEST_KEY in keys:
        return True
    return bool(prefix) and store.exists(MANIFEST_KEY)


def _matching(rows: list[SourceRow], search: str) -> list[SourceRow]:
    """Rows whose text contains `search`, case-insensitively.

    The `domains:` tag is searchable text too. Typing "literacy" should reach a
    source that carries `strategy:adult-literacy-numeracy` even when neither its
    title nor its excerpt says the word.
    """
    needle = search.lower()
    return [
        r
        for r in rows
        if needle in r.title.lower()
        or needle in r.excerpt.lower()
        or needle in r.path.lower()
        or any(needle in d.lower() for d in r.domains)
    ]


def _ordered(rows: list[SourceRow], search: str) -> list[SourceRow]:
    """The order this listing has always used, preserved exactly.

    Unsearched, rows come back in key order — the filename's date prefix, which
    the naming convention writes *from* `fetched_at`. Searched, they come back in
    `fetched_at` order. The two agree for anything following the convention and
    differ for older files, and unifying them would change what the screen shows
    for reasons that have nothing to do with an index.
    """
    if search:
        # Damaged rows have no fetched_at and sort last.
        return sorted(rows, key=lambda r: r.fetched_at, reverse=True)
    return sorted(rows, key=lambda r: r.path.rsplit("/", 1)[-1], reverse=True)


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

    **Two paths, and which one runs depends on whether the corpus is indexed.**
    With a manifest every row is affordable, so narrowing and searching happen on
    rows and a search costs one read. Without one the old rules apply: a page
    load reads only its page, and a search reads everything because it has to.
    An unindexed corpus must keep working — see `INDEX-08`.
    """
    raw_keys = store.list(prefix)
    all_keys = _source_keys(raw_keys)
    # Counted BEFORE any narrowing, which is the whole job: a narrowed list has
    # to be able to say what it is a subset of. Measured after the domain filter
    # it reported 406 of 406 — technically a number, and useless.
    corpus_total = len(all_keys)

    if domain:
        all_keys = [k for k in all_keys if _in_domain(k, domain)]
    domains = sorted({_domain_of(k) for k in all_keys})

    defs = list_domain_defs(store, prefix) if focus else []
    focus_dirs = focus_folders(focus, defs) if focus else []

    manifest = load_manifest(store) if _is_indexed(store, raw_keys, prefix) else None

    if manifest is not None:
        # Keys the manifest has never seen are read individually, so an index a
        # few captures behind costs a few reads rather than a rebuild. The one
        # thing this cannot see is an edit in place — same key, changed content.
        uncovered = [k for k in all_keys if k not in manifest.entries]
        blobs = _read_many(store, uncovered)
        rows = []
        for key in all_keys:
            entry = manifest.entries.get(key)
            if entry is None:
                entry = _entry_for(key, blobs.get(key, KeyError(key)))
            rows.append(row_from_entry(entry, bin_store))
        if focus:
            # Narrowed on the ROW, so a source referencing a focus whose folder
            # it does not live under is found. That case used to be reachable
            # only under search; see Strategy-Focus §4 and `FOCUS-07`.
            #
            # `any_match` rather than `in`: a domain reference CASCADES, so
            # focusing `strategy` reaches `strategy:workforce-development` — on
            # the separator, never on the string.
            rows = [
                r for r in rows if in_any_folder(r.path, focus_dirs) or any_match(r.domains, focus)
            ]
        if search:
            rows = _matching(rows, search)
        return Listing(
            rows=_ordered(rows, search)[offset : offset + limit],
            total=len(rows),
            domains=domains,
            corpus_total=corpus_total,
            index_stale=bool(uncovered),
        )

    # ---- unindexed ---------------------------------------------------------
    if focus and not search:
        # Narrowed on the KEY, because the alternative is opening every file to
        # check a tag. Exact for reach-edu today: all 241 tagged sources sit in
        # the folder their tag names and none carries a second tag.
        all_keys = [k for k in all_keys if in_any_folder(k, focus_dirs)]
        domains = sorted({_domain_of(k) for k in all_keys})

    # A search has to look at everything. A page load does not, and pretending
    # otherwise costs 845 network reads to show 50 rows.
    total = len(all_keys)
    paged = not search
    keys = _page_keys(all_keys, offset, limit) if paged else all_keys

    blobs = _read_many(store, keys)
    rows = [row_from_entry(_entry_for(k, blobs.get(k, KeyError(k))), bin_store) for k in keys]

    if search:
        rows = _matching(rows, search)
        if focus:
            # Every file was opened for the search, so the reference is visible
            # here even on a source living outside the focus's folder — strictly
            # better than the key-level narrowing, and free at this point.
            rows = [
                r for r in rows if in_any_folder(r.path, focus_dirs) or any_match(r.domains, focus)
            ]
        total = len(rows)

    if paged:
        # Already ordered and windowed by key; re-slicing would drop rows.
        return Listing(rows=rows, total=total, domains=domains, corpus_total=corpus_total)

    return Listing(
        rows=_ordered(rows, search)[offset : offset + limit],
        total=total,
        domains=domains,
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
