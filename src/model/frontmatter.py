"""Read and write YAML frontmatter without losing what we did not expect.

Two failures this tree already paid for live here, both promoted from silent to
loud. Neither was a schema problem — the schema was written down and correct in
both cases. They were *parser* and *serializer* problems, which is why they were
invisible.

**Stranded content.** A stray `---` on its own line closes the frontmatter
early. On 2026-07-14 that hid 13 of ImmuneCo's 93 sources for three weeks: they
were on disk, a grep found them, a diff looked fine, only the parse disagreed.
Every consumer worked with 80 and none of them knew. So content after the
closing fence that still looks like frontmatter raises `StrandedContent` rather
than being quietly absorbed into the body.

**Unknown-key loss.** A serializer that emits only the keys it recognises will
delete anything a newer writer added. That silently stripped `sensitivity` —
the flag governing whether a source may be cited outside the firm — from eight
sources. So parsing keeps everything, and rendering re-emits everything.
"""

from __future__ import annotations

import re
from typing import Any

import yaml


class _NoDatesLoader(yaml.SafeLoader):
    """A loader that leaves date-shaped scalars as the strings they were.

    PyYAML resolves `2025-03-01` to a `datetime.date` and
    `2026-06-27T14:31:00Z` to a `datetime`. Round-tripping through those types
    silently REFORMATS what was on disk — `Z` becomes `+00:00`, a date loses its
    quoting — which is a third variety of the quiet mutation this module exists
    to prevent. Files are the truth; the parser does not get to reinterpret
    them.
    """


_NoDatesLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class StrandedContent(ValueError):
    """Frontmatter-looking content found after the closing fence."""


_FENCE = re.compile(r"^---\s*$")
#: `key: value` at column zero, the shape an orphaned frontmatter line takes.
#: Deliberately narrow: a markdown heading, a list item, a quote, an indented
#: line, or a URL in prose must not match, or every ordinary body trips it.
_ORPHAN_KEY = re.compile(r"^([a-z][a-z0-9_]{2,}):(?:\s|$)")

#: Body lines that look like keys but are ordinary prose punctuation.
_ORPHAN_ALLOW = frozenset({"http", "https", "note", "e_g", "i_e"})


def _looks_stranded(body: str) -> str | None:
    """Return the first orphaned frontmatter key in `body`, if any.

    Only lines before the first blank line are considered. Real stranded
    frontmatter is a contiguous run of `key: value` immediately after the fence;
    a body that opens with prose and mentions `foo: bar` later is not damaged.
    """
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line:
            return None  # a blank line means ordinary body started
        match = _ORPHAN_KEY.match(line)
        if not match:
            return None
        key = match.group(1)
        if key in _ORPHAN_ALLOW:
            return None
        return key
    return None


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split `text` into (frontmatter mapping, body).

    Raises `StrandedContent` when the body carries orphaned `key: value` lines
    that were almost certainly meant to be frontmatter.
    """
    lines = text.splitlines(keepends=True)
    if not lines or not _FENCE.match(lines[0].rstrip("\n")):
        return {}, text

    for index in range(1, len(lines)):
        if _FENCE.match(lines[index].rstrip("\n")):
            raw = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            break
    else:
        # An opening fence with no closing one. The whole thing is frontmatter
        # as far as YAML is concerned; treat it as body rather than guessing.
        return {}, text

    loaded = yaml.load(raw, Loader=_NoDatesLoader) if raw.strip() else {}
    data: dict[str, Any] = loaded if isinstance(loaded, dict) else {}

    stranded = _looks_stranded(body.lstrip("\n"))
    if stranded is not None:
        raise StrandedContent(
            f"frontmatter-shaped content after the closing fence, starting at "
            f"{stranded!r}. A stray '---' almost certainly truncated the "
            f"frontmatter — this is the failure that hid 13 of ImmuneCo's 93 "
            f"sources for three weeks. Fix the file rather than the parser."
        )

    return data, body


def render_frontmatter(data: dict[str, Any], body: str, order: list[str]) -> str:
    """Render `data` + `body` back to a file, keys in `order` first.

    Keys not in `order` are emitted after those that are, in their original
    order — never dropped.
    """
    ordered: dict[str, Any] = {}
    for key in order:
        if key in data:
            ordered[key] = data[key]
    for key, value in data.items():
        if key not in ordered:
            ordered[key] = value

    if not ordered:
        return body

    dumped = yaml.safe_dump(
        ordered,
        sort_keys=False,  # FIELD_ORDER is the point; alphabetical would undo it
        allow_unicode=True,
        default_flow_style=False,
        width=10_000,  # never wrap — a wrapped URL is a broken URL
    )
    return f"---\n{dumped}---\n{body}"
