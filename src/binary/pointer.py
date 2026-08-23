"""Adding a pointer to an existing wrapper, surgically.

Implements `context-v/specs/Binary-Ingest-And-Bin-Store.md` Behaviour 12, and
exists because the obvious approach was tried and was wrong.

`SourceFile.parse()` → `render()` is a **re-serialization**, not a round trip. It
reorders keys into `FIELD_ORDER`, normalises YAML quoting, coerces timestamps to
strings, and silently drops nested keys the dataclass does not model. Run over 34
real client wrappers on 2026-08-22 it produced 250 discrepancies — including
dropping `binary_asset.content_type` and `size_bytes`, and redefining `sha256`
from *what the publisher served* to *what we stored*. That change was reverted
before it was committed. See
`context-v/issues/Orphaned-Bin-Objects-From-A-Half-Migration.md`.

So this module does not parse and re-emit. **It edits the bytes it means to edit
and leaves every other byte alone**, which is the only property worth having when
writing into a corpus someone else's work depends on.

Three rules:

1. **Never redefine an existing key.** `sha256`, `size_bytes` and `content_type`
   keep the meanings they already have — the source file as the publisher served
   it. The optimized artifact gets *new* names. A key whose meaning silently
   changes is worse than a missing key, because nothing can tell which era a file
   is from.
2. **Only add.** The patch writes `binary_key`, `optimized`, and, when there is
   one, `optimized_sha256` / `optimized_bytes`. It never removes or rewrites a
   line it did not author.
3. **The invariant is checkable.** Strip the lines this module added and the
   result must equal the original, byte for byte. That is `BIN-25`, and it is
   the gate every migration passes before it touches anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The keys this module owns. Everything else in a `binary_asset:` block belongs
#: to whoever wrote it and is never touched.
OWNED_KEYS = ("binary_key", "optimized", "optimized_sha256", "optimized_bytes")

_BLOCK = re.compile(r"^binary_asset:[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Pointer:
    """What a migration adds to a wrapper.

    `binary_key` is the *working* copy — the optimized artifact when one was
    accepted, otherwise the source. `source_key` is derivable from the wrapper's
    existing `sha256` and is therefore not stored: a second copy of a fact is a
    second thing that can drift.
    """

    binary_key: str
    optimized: bool
    optimized_sha256: str = ""
    optimized_bytes: int = 0
    #: The publisher's file. Written ONLY when creating a block from nothing —
    #: an existing block already records these and they are never overwritten.
    source_sha256: str = ""
    source_bytes: int = 0

    def creation_lines(self, indent: str = "  ") -> list[str]:
        """A whole block, for a wrapper that had none. Carries the source facts
        because nothing else in the file records them."""
        out = []
        if self.source_sha256:
            out.append(f"{indent}sha256: {self.source_sha256}")
        if self.source_bytes:
            out.append(f"{indent}size_bytes: {self.source_bytes}")
        return out + self.lines(indent)

    def lines(self, indent: str = "  ") -> list[str]:
        out = [f"{indent}binary_key: {self.binary_key}"]
        out.append(f"{indent}optimized: {'true' if self.optimized else 'false'}")
        if self.optimized:
            out.append(f"{indent}optimized_sha256: {self.optimized_sha256}")
            out.append(f"{indent}optimized_bytes: {self.optimized_bytes}")
        return out


def _block_bounds(text: str) -> tuple[int, int, str] | None:
    """Line indices spanning an existing `binary_asset:` block, plus its indent."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "binary_asset:"), None)
    if start is None:
        return None
    indent = "  "
    end = start + 1
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() == "" or not ln.startswith((" ", "\t")):
            break
        if end == start + 1:
            indent = ln[: len(ln) - len(ln.lstrip())]
        end = i + 1
    return start, end, indent


def strip_pointer(text: str) -> str:
    """Remove exactly the lines this module adds. The inverse of `apply_pointer`."""
    bounds = _block_bounds(text)
    if bounds is None:
        return text
    start, end, indent = bounds
    lines = text.splitlines(keepends=True)
    kept = [
        ln
        for i, ln in enumerate(lines)
        if not (start < i < end and ln.strip().split(":")[0] in OWNED_KEYS)
    ]
    # If the block held nothing but our keys, we created it — remove it too, so
    # `strip(apply(x)) == x` holds for wrappers that had no block to begin with.
    remaining = [ln for ln in kept[start + 1 :] if ln.startswith((" ", "\t")) and ln.strip()]
    if not remaining or not any(
        kept[i].startswith((" ", "\t")) and kept[i].strip()
        for i in range(start + 1, min(start + 2, len(kept)))
    ):
        kept = kept[:start] + kept[start + 1 :]
    return "".join(kept)


def _frontmatter_end(text: str) -> int | None:
    """Index of the closing `---` line, so a new block lands inside the frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    return next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)


def apply_pointer(text: str, pointer: Pointer) -> str:
    """Add (or refresh) the pointer keys inside `binary_asset:`, touching nothing else.

    Creates the block when a wrapper has none — one of the 34 real wrappers did
    not, and a capture that failed before recording anything is the normal way
    that happens.

    Idempotent: applying twice is applying once. Re-applying with a different
    pointer replaces only the owned keys.
    """
    text = strip_pointer(text)
    bounds = _block_bounds(text)
    lines = text.splitlines(keepends=True)

    if bounds is None:
        end = _frontmatter_end(text)
        if end is None:
            return text  # not a frontmatter document; nothing safe to do
        block = ["binary_asset:\n"] + [ln + "\n" for ln in pointer.creation_lines("  ")]
        return "".join(lines[:end] + block + lines[end:])

    _, blk_end, indent = bounds
    addition = [ln + "\n" for ln in pointer.lines(indent)]
    return "".join(lines[:blk_end] + addition + lines[blk_end:])


def has_pointer_for(text: str, source_sha256: str) -> bool:
    """Whether this wrapper already points at an object for exactly this source.

    Matches on the wrapper's own `sha256` — the publisher's file — because that
    is the identity that does not change when we re-optimize.
    """
    if "binary_key:" not in text:
        return False
    m = re.search(r"^\s*sha256:\s*\"?([0-9a-f]{64})\"?", text, re.MULTILINE)
    return bool(m and m.group(1) == source_sha256)
