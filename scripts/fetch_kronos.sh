#!/usr/bin/env bash
# Clone Kronos at a pinned commit. Never executes anything from the clone.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PINNED_COMMIT="67b630e67f6a18c9e9be918d9b4337c960db1e9a"
DEST="$ROOT/third_party/kronos"
if [ ! -d "$DEST/.git" ]; then
  git clone https://github.com/shiyu-coder/Kronos "$DEST"
fi
git -C "$DEST" fetch --quiet origin
git -C "$DEST" checkout --quiet "$PINNED_COMMIT"
echo "Kronos at $(git -C "$DEST" rev-parse HEAD)"
