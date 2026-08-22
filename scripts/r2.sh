#!/usr/bin/env bash
# Run any rclone command against this workspace's R2 bucket, with credentials
# loaded from .env at run time and never persisted to ~/.config/rclone/rclone.conf.
#
# The remote is called `r2:`. Everything after the script name is passed to
# rclone verbatim, so anything rclone can do, this can do.
#
#   ./scripts/r2.sh tree   r2:reach-edu/corpora/live --level 2
#   ./scripts/r2.sh ls     r2:reach-edu/corpora/live
#   ./scripts/r2.sh size   r2:reach-edu/corpora/live
#   ./scripts/r2.sh ncdu   r2:reach-edu/corpora/live      # interactive browser
#   ./scripts/r2.sh cat    r2:reach-edu/corpora/live/README.md
#   ./scripts/r2.sh copy   r2:reach-edu/corpora/live ~/somewhere   # pull a copy down
#
# Bare `./scripts/r2.sh` with no arguments prints the destination and a listing
# summary, which is usually the question being asked.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v rclone >/dev/null || { echo "rclone not installed: brew install rclone" >&2; exit 1; }

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

export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="$CLOUDFLARE_R2_API_ENDPOINT"
export RCLONE_CONFIG_R2_REGION=auto
export RCLONE_CONFIG_R2_ACL=private

LIVE="r2:${CORPORA_R2_BUCKET}/${CORPORA_R2_PREFIX:-}live"

if [[ $# -eq 0 ]]; then
  echo "bucket : ${CORPORA_R2_BUCKET}"
  echo "prefix : ${CORPORA_R2_PREFIX:-}"
  echo "live   : ${LIVE}"
  echo
  rclone size "$LIVE"
  echo
  echo "top level:"
  rclone lsd "$LIVE" | awk '{printf "  %s\n", $NF}'
  echo
  echo "try: $0 tree $LIVE --level 2   |   $0 ncdu $LIVE   |   $0 cat $LIVE/README.md"
  exit 0
fi

exec rclone "$@"
