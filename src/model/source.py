"""One source's file: frontmatter scalars plus a markdown body.

Implements the canonical schema in
`context-v/blueprints/Source-File-Schema-Reconciliation.md`, which reconciled
three implementations that had converged independently — augment-it's
`content-ingest/src/corpus.ts`, memopop's `source-with-extracts-md`, and the
strategy-curator view model. Adoption is copy-from, knots-style; there is no
shared package across a Python core, a Node service and a Tauri app.

Four rules carried from that blueprint, each load-bearing:

1. **`fetched_at` is not `published_at`.** When we pulled it is not when it was
   written. Conflating them makes staleness unanswerable.
2. **Two orthogonal lifecycle axes.** `status` is the analyst's decision;
   `content_pulled` is how much is on disk. A source can be `promoted` with
   nothing fetched yet, or a `candidate` already cached. One field cannot say
   that.
3. **`verdict` is a person, `machine_verdict` is a machine.** Reachability is
   not approval — memopop learned this expensively when 34 sources carried
   verdicts reading "HTTP 200 (body verified)" and were counted as approved.
   Nothing in this codebase writes `verdict`.
4. **Extracts live in the body, never in YAML.** Quotes and stats are
   punctuation-heavy strings full of `: " $ % [ ] |` — every character that
   breaks YAML. The markdown parse *is* the structured extraction, so there is
   no second copy to drift. This module carries the body verbatim and never
   generates an `# Extracts` section.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields
from typing import Any

from src.model.frontmatter import parse_frontmatter, render_frontmatter

#: Fixed, not alphabetical, so a git diff of a curated file shows what changed
#: rather than a reshuffle. Grouped the way the blueprint groups them.
FIELD_ORDER = [
    # identity
    "url",
    "normalized_url",
    "title",
    "publisher",
    "authors",
    # time — never conflate these two
    "fetched_at",
    "published_at",
    # lifecycle — two orthogonal axes, both kept
    "status",
    "content_pulled",
    "excerpt",
    "description",
    # provenance
    "origin",
    "origin_detail",
    # membership — aboutness, many-to-many, never nesting
    "domains",
    "sections",
    "tags",
    "rank",
    "sensitivity",
    # judgment — the person/machine split is permanent
    "verdict",
    "verdict_reason",
    "machine_verdict",
    "confidence",
    "note",
    # binary companion
    "binary_asset",
    # catch-all
    "extra_metadata",
]

#: Earlier generations' names for canonical fields. Measured against the real
#: reach-edu corpus on 2026-08-08: 637 of 845 files use `exact_url` and only 241
#: use `url`; 179 use `published_date`. A reader that does not know these is
#: blind to most of the corpus it exists to read.
#:
#: Read-only. The original key is remembered and re-emitted on write, because
#: reading a file is not consent to migrate its schema — that is a deliberate
#: operation someone chooses, not a side effect of opening it.
FIELD_ALIASES = {
    "exact_url": "url",
    "published_date": "published_at",
}

VALID_STATUS = ("candidate", "promoted", "archived", "rejected")


def _defaults() -> dict[str, Any]:
    """Each modelled field's default, for the do-not-accrete check."""
    out: dict[str, Any] = {}
    for f in fields(SourceFile):
        if f.default is not MISSING:
            out[f.name] = f.default
        elif f.default_factory is not MISSING:
            out[f.name] = f.default_factory()
    return out


#: Recorded even when the download failed — a failure is a fact, not an absence.
VALID_DOWNLOAD_STATUS = (
    "ok",
    "size_capped",
    "http_error",
    "unsupported_type",
    "fetch_failed",
)


@dataclass
class BinaryAsset:
    """A PDF or other binary riding alongside its markdown.

    Present even on failure: `download_status` distinguishes "we never tried"
    from "we tried and it 403'd", which the absence of a block cannot.
    """

    filename: str = ""
    bytes: int = 0
    sha256: str = ""
    downloaded_at: str = ""
    download_status: str = ""


@dataclass
class SourceFile:
    """Only `url` is required. Everything else degrades gracefully."""

    url: str
    normalized_url: str = ""
    title: str = ""
    publisher: str = ""
    authors: list[str] = field(default_factory=list)

    fetched_at: str = ""
    published_at: str = ""

    status: str = "candidate"
    content_pulled: bool = False
    excerpt: str = ""
    description: str = ""

    origin: str = ""
    origin_detail: dict[str, Any] = field(default_factory=dict)

    domains: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    rank: int = 0
    sensitivity: str = ""

    #: Written by a person. Never by this codebase.
    verdict: str = ""
    verdict_reason: str = ""
    #: Written by a validator. Never promoted to `verdict`.
    machine_verdict: str = ""
    confidence: str = ""
    note: str = ""

    binary_asset: BinaryAsset | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    #: The markdown after the frontmatter, carried verbatim.
    body: str = ""

    #: Frontmatter keys this model does not model. Preserved so a newer writer's
    #: fields are never deleted by an older reader — the failure that stripped
    #: `sensitivity` from eight sources.
    unknown: dict[str, Any] = field(default_factory=dict)

    #: canonical name -> the alias this file actually used, so a round-trip
    #: writes back what was there rather than quietly renaming it.
    #: compare=False: this is provenance of the parse, not content. Two sources
    #: with the same fields are the same source however their keys were spelled.
    aliases_used: dict[str, str] = field(default_factory=dict, compare=False)

    #: Keys the file actually carried. A parsed source re-emits exactly those;
    #: it does not accrete defaults it never had. Writing `status: candidate`
    #: onto a file whose `inbox_status` says `discarded` is not a harmless
    #: default — it is an assertion the file never made.
    present_keys: set[str] = field(default_factory=set, compare=False)

    #: Whether the file had frontmatter at all. A corpus directory holds plain
    #: markdown too — READMEs, AGENTS.md, notes — and re-rendering one of those
    #: must not GRAFT frontmatter onto it. Defaults True so a constructed (not
    #: parsed) SourceFile still renders its frontmatter.
    had_frontmatter: bool = True

    def to_frontmatter(self) -> dict[str, Any]:
        """The mapping to serialise, unknown keys included.

        Empty values are omitted so a `url`-only file stays a `url`-only file
        rather than accreting two dozen blank keys on first read.
        """
        if not self.had_frontmatter:
            return {}

        defaults = _defaults()
        data: dict[str, Any] = {}
        for name in FIELD_ORDER:
            if name == "binary_asset":
                if self.binary_asset is not None:
                    data["binary_asset"] = {
                        k: v for k, v in vars(self.binary_asset).items() if v not in ("", 0)
                    }
                continue
            value = getattr(self, name, None)
            emit_as = self.aliases_used.get(name, name)
            if value in (None, "", [], {}):
                continue
            # `rank: 0` means unranked, which is what absence already says.
            # `content_pulled: false` is NOT the same as absent — it asserts we
            # deliberately have not fetched, which is the two-tier gate's whole
            # record. So this suppression is one field, not a rule about falsy.
            if name == "rank" and not value:
                continue
            # A PARSED source re-emits what it carried and nothing more, so
            # reading a file never accretes defaults it did not assert. A NEWLY
            # CONSTRUCTED one emits everything non-empty, because a fresh source
            # file that omits `status: candidate` is not stating its own
            # lifecycle — and the whole schema turns on that field.
            if self.present_keys and emit_as not in self.present_keys:
                if value == defaults.get(name):
                    continue
            data[emit_as] = value

        for key, value in self.unknown.items():
            data.setdefault(key, value)
        return data

    @classmethod
    def from_frontmatter(cls, data: dict[str, Any], body: str = "") -> SourceFile:
        """Build from a parsed mapping, routing unrecognised keys to `unknown`."""
        known = {f.name for f in fields(cls)} - {
            "body",
            "unknown",
            "aliases_used",
            "binary_asset",
        }
        kwargs: dict[str, Any] = {}
        unknown: dict[str, Any] = {}
        aliases_used: dict[str, str] = {}

        for key, value in (data or {}).items():
            if key == "binary_asset":
                continue
            if key in known:
                kwargs[key] = value
            elif key in FIELD_ALIASES:
                canonical = FIELD_ALIASES[key]
                # Canonical wins if both are present — a file carrying both is
                # mid-migration, and the newer key is the intended one.
                if canonical not in data:
                    kwargs[canonical] = value
                    aliases_used[canonical] = key
                else:
                    unknown[key] = value
            else:
                unknown[key] = value

        asset_data = (data or {}).get("binary_asset")
        asset = None
        if isinstance(asset_data, dict):
            asset_fields = {f.name for f in fields(BinaryAsset)}
            asset = BinaryAsset(**{k: v for k, v in asset_data.items() if k in asset_fields})

        kwargs.setdefault("url", "")
        return cls(
            binary_asset=asset,
            body=body,
            unknown=unknown,
            aliases_used=aliases_used,
            had_frontmatter=bool(data),
            present_keys=set(data or {}),
            **kwargs,
        )

    def render(self) -> str:
        """The complete file: frontmatter plus body."""
        return render_frontmatter(self.to_frontmatter(), self.body, FIELD_ORDER)

    @classmethod
    def parse(cls, text: str) -> SourceFile:
        """Read a complete file. Raises `StrandedContent` on a truncated fence."""
        data, body = parse_frontmatter(text)
        return cls.from_frontmatter(data, body)
