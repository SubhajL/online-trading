#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOURCE="$REPO_ROOT/contracts/gen/ts/index.ts"
VENDORED="$REPO_ROOT/app/bff/src/contracts/gen/index.ts"

if ! diff -q "$SOURCE" "$VENDORED" > /dev/null 2>&1; then
  echo "ERROR: Vendored contracts out of sync."
  echo "  Source:   $SOURCE"
  echo "  Vendored: $VENDORED"
  echo ""
  echo "Run: cp $SOURCE $VENDORED"
  diff --unified "$SOURCE" "$VENDORED" || true
  exit 1
fi

echo "Contracts in sync."
