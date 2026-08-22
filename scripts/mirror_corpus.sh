#!/usr/bin/env bash
# Mirror a local corpus tree up to its R2 `live/` prefix, one direction only.
#
# This is Phase 1 of ai-labs/context-v/plans/Sync-Corpora-to-R2-and-Show-Clients-What-Changed.md.
# It is deliberately NOT `rclone sync` — `copy` never deletes at the destination,
# because the destination is a client-owned bucket and a one-way mirror should not
# be able to remove anything there. If pruning is ever wanted it should be a
# separate, explicit decision, not a flag on this script.
#
# The laptop and git remain the source of truth. This makes a second copy that a
# human can pull down with rclone and read with no corpora-builder installed —
# the "files-as-truth, hand-recoverable" property the plan turns on.
#
#   ./scripts/mirror_corpus.sh <source-dir> [--verify] [--dry-run]
#
# Env comes from .env: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
# CLOUDFLARE_R2_API_ENDPOINT, CORPORA_R2_BUCKET, CORPORA_R2_PREFIX.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-}"
shift || true
VERIFY=0
DRY=""
for arg in "$@"; do
  case "$arg" in
    --verify)  VERIFY=1 ;;
    --dry-run) DRY="--dry-run" ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "usage: $0 <source-dir> [--verify] [--dry-run]" >&2
  exit 2
fi

command -v rclone >/dev/null || { echo "rclone not installed: brew install rclone" >&2; exit 1; }

# Load only the keys we need, without printing any of them.
eval "$(python3 - "$REPO_ROOT/.env" <<'PY'
import shlex, sys
from pathlib import Path
WANT = {"R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_API_ENDPOINT",
        "CORPORA_R2_BUCKET", "CORPORA_R2_PREFIX"}
for line in Path(sys.argv[1]).read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        k = k.strip(); v = v.strip().strip('"').strip("'")
        if k in WANT:
            print(f"export {k}={shlex.quote(v)}")
PY
)"

for k in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY CLOUDFLARE_R2_API_ENDPOINT CORPORA_R2_BUCKET; do
  [[ -n "${!k:-}" ]] || { echo "missing in .env: $k" >&2; exit 1; }
done

DEST="r2:${CORPORA_R2_BUCKET}/${CORPORA_R2_PREFIX:-}live/"

# Configure the remote inline so nothing has to be persisted to rclone.conf.
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="$CLOUDFLARE_R2_API_ENDPOINT"
export RCLONE_CONFIG_R2_REGION=auto
export RCLONE_CONFIG_R2_ACL=private

echo "source: $SRC"
echo "dest:   $DEST"
echo

rclone copy "$SRC" "$DEST" \
  --exclude ".DS_Store" --exclude "**/.DS_Store" \
  --transfers 16 --checkers 16 --stats 20s --stats-one-line $DRY

[[ -n "$DRY" ]] && exit 0

echo
rclone size "$DEST"

if [[ "$VERIFY" -eq 1 ]]; then
  echo
  echo "=== round trip: pulling down fresh and comparing sha256 ==="
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  rclone copy "$DEST" "$TMP" --transfers 16 --checkers 16 --stats-one-line

  ( cd "$SRC" && find . -type f ! -name '.DS_Store' -exec shasum -a 256 {} \; | sort -k2 ) > "$TMP.src"
  ( cd "$TMP"  && find . -type f -exec shasum -a 256 {} \; | sort -k2 ) > "$TMP.dst"

  echo "source files:    $(wc -l < "$TMP.src" | tr -d ' ')"
  echo "recovered files: $(wc -l < "$TMP.dst" | tr -d ' ')"
  if diff -q "$TMP.src" "$TMP.dst" >/dev/null; then
    echo "VERIFIED: byte-identical round trip."
  else
    echo "MISMATCH:" >&2
    diff "$TMP.src" "$TMP.dst" | head -20 >&2
    rm -f "$TMP.src" "$TMP.dst"
    exit 1
  fi
  rm -f "$TMP.src" "$TMP.dst"
fi
