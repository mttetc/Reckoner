#!/usr/bin/env sh
# Build a pinned WoWSims Classic CLI (wowsimcli, with the embedded item database) for the
# World of Warcraft Classic engine.
#
#   backend/scripts/install_wowsims.sh [DEST]      default DEST: <repo>/.engines/wowsims-classic
#
# Requires git, go (1.23+), protoc and protoc-gen-go on PATH (brew install go protobuf protoc-gen-go;
# on Debian/Ubuntu: apt install protobuf-compiler + go install google.golang.org/protobuf/cmd/protoc-gen-go@latest).
# The binary is DEST/build/wowsimcli; point RECKONER_WOWSIMS_BIN at it. The checkout also serves
# item names and talent trees (assets/database/db.json, ui/core/talents/trees). Bump WOWSIMS_COMMIT
# deliberately: the CLI's version (that commit) ends up in every simulated metric's provenance.
set -eu

WOWSIMS_REPO="https://github.com/wowsims/classic.git"
WOWSIMS_COMMIT="${WOWSIMS_COMMIT:-7779ebbf79dc7f1341e6ab939b28a3402c9a730a}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-$ROOT/.engines/wowsims-classic}"

for tool in git go protoc protoc-gen-go; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: '$tool' not found" >&2
    exit 1
  fi
done

if [ -x "$DEST/build/wowsimcli" ] && [ "$(git -C "$DEST" rev-parse HEAD 2>/dev/null)" = "$WOWSIMS_COMMIT" ]; then
  echo "wowsimcli already built at $DEST/build/wowsimcli ($WOWSIMS_COMMIT)"
  exit 0
fi

if [ ! -d "$DEST/.git" ]; then
  git clone --quiet --filter=blob:none "$WOWSIMS_REPO" "$DEST"
fi
git -C "$DEST" fetch --quiet origin "$WOWSIMS_COMMIT"
git -C "$DEST" checkout --quiet "$WOWSIMS_COMMIT"

cd "$DEST"
protoc -I=./proto --go_out=./sim/core ./proto/*.proto
SHORT="$(git rev-parse --short HEAD)"
go build -o build/wowsimcli --tags=with_db -ldflags="-X 'main.Version=$SHORT'" ./cmd/wowsimcli/cli_main.go
echo "wowsimcli $("$DEST/build/wowsimcli" version) built at $DEST/build/wowsimcli"
