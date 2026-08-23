"""The corpus as a folder tree, derived from keys alone.

Implements `context-v/specs/Corpus-Tree.md`.

The whole module is one pure function over a list of strings. That is not
minimalism for its own sake — it is the same rule `list_domains` established and
that `/api/meta` learned the hard way: **structure lives in the key.** Painting
944 objects costs one `list()` call and zero file reads. Deriving the same shape
by opening files took 20.6 seconds against R2 and looked, from the outside, like
a hung window.

Adapted from `flave-ai/src-tauri/src/lib.rs::walk`, which does this against a
real directory with `fs::read_dir`. What travels is the node shape and the
folders-first ordering; what cannot travel is the traversal, because a corpus is
an object store with no directories to walk. The cross-app pattern is written up
in `ai-labs/context-v/blueprints/Show-The-Filesystem-Of-A-Workspace.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeNode:
    """One row in the tree.

    `path` is what you would type: a file's key, or a folder's prefix ending in
    `/`. Always corpus-relative — the client never receives an absolute path and
    so cannot construct one that escapes the corpus. flave-ai enforces the same
    invariant in Rust, where the stakes are higher because the other side of the
    boundary is a real disk.
    """

    name: str
    path: str
    is_dir: bool
    children: list[TreeNode] = field(default_factory=list)
    #: Files at any depth beneath this node. Zero for a file.
    count: int = 0

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "count": self.count,
            "children": [c.to_json() for c in self.children],
        }


def _sort(nodes: list[TreeNode]) -> list[TreeNode]:
    """Folders first, then alphabetical — flave-ai's rule, and the order a person
    expects. Within a kind it is plain alphabetical, deliberately: the domain
    combobox briefly sorted siblings by name length and the result was
    indistinguishable from random."""
    return sorted(nodes, key=lambda n: (not n.is_dir, n.name))


#: Prefixes whose immediate subdirectory level is a storage optimisation rather
#: than information. `bin/` fans out by the first two hex characters of the
#: digest so one directory never holds thousands of entries — restic and Kopia
#: do the same. Rendered literally that is 55 folders named `00`, `05`, `09`,
#: each holding exactly one file, and it is the first thing the tree shows
#: because `bin` sorts before `live`. Every object stays visible; only the
#: meaningless level is collapsed. Same instinct as flave-ai skipping dotfiles:
#: the app's business, not the reader's.
FLATTENED = ("bin/",)


def _flatten_fanout(key: str) -> str:
    """Drop a content-addressed fan-out segment: `bin/00/<sha>.pdf` → `bin/<sha>.pdf`."""
    for prefix in FLATTENED:
        if key.startswith(prefix):
            rest = key[len(prefix) :]
            head, slash, tail = rest.partition("/")
            if slash and len(head) == 2 and all(c in "0123456789abcdef" for c in head):
                return prefix + tail
    return key


def build_tree(keys: list[str]) -> list[TreeNode]:
    """The corpus's directory structure, from its keys.

    Pure: no store, no I/O, nothing to mock. A key with no `/` is a root-level
    file; an empty input is an empty list rather than a phantom root.

    A content-addressed fan-out level is flattened for display — see `FLATTENED`
    — but a file node's `path` is always its real key.
    """
    roots: dict[str, TreeNode] = {}

    for key in sorted(keys):
        display = _flatten_fanout(key)
        parts = [p for p in display.split("/") if p]
        if not parts:
            continue

        level = roots
        prefix = ""
        # Every part but the last is a folder on the way down.
        for part in parts[:-1]:
            prefix = f"{prefix}{part}/"
            node = level.get(part)
            if node is None:
                node = TreeNode(name=part, path=prefix, is_dir=True)
                level[part] = node
            node.count += 1  # counts every file beneath, at any depth
            level = _children_index(node)

        leaf = parts[-1]
        if leaf not in level:
            # `path` stays the REAL key — the tree flattens what it draws, never
            # what it hands back, or opening a binary would 404.
            level[leaf] = TreeNode(name=leaf, path=key, is_dir=False)

    return _materialise(roots)


# Folders are assembled through a name→node index so a second key under the same
# folder finds the existing node instead of creating a sibling with one child.
# The index is stashed on the node and dropped when the tree is materialised.
_INDEX = "_index"


def _children_index(node: TreeNode) -> dict[str, TreeNode]:
    idx = getattr(node, _INDEX, None)
    if idx is None:
        idx = {}
        setattr(node, _INDEX, idx)
    return idx


def _materialise(level: dict[str, TreeNode]) -> list[TreeNode]:
    out = []
    for node in level.values():
        idx = getattr(node, _INDEX, None)
        if idx:
            node.children = _materialise(idx)
            delattr(node, _INDEX)
        out.append(node)
    return _sort(out)
