#!/usr/bin/env sh
# Install a pinned Path of Building checkout for the headless engine (SPEC § 5 B).
#
#   backend/scripts/install_pob.sh [DEST]      default DEST: <repo>/.engines/pob
#
# Requires git and luajit (`brew install luajit` / `apt install luajit`). The checkout is sparse:
# tree sprite PNGs are excluded (≈340 MB) — headless PoB stubs image loading and never reads them.
# Bump POB_COMMIT deliberately: the engine version ends up in every recalculated metric's provenance.
set -eu

POB_REPO="https://github.com/PathOfBuildingCommunity/PathOfBuilding.git"
POB_COMMIT="${POB_COMMIT:-ed354c2f8c42e148bc904c7508dbe851fb2cf952}"   # v2.67.2 line, 2026-08-27
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-$ROOT/.engines/pob}"

if [ -d "$DEST/.git" ]; then
  echo "reusing $DEST"
else
  mkdir -p "$(dirname "$DEST")"
  git clone --quiet --no-checkout --filter=blob:none "$POB_REPO" "$DEST"
fi
cd "$DEST"
git sparse-checkout init --no-cone
printf '%s\n' '/*' '!/src/TreeData/**/*.png' '!/src/TreeData/**/*.webp' '!/runtime-win32.zip' '!/runtime/*.dll' > .git/info/sparse-checkout
git fetch --quiet --depth 1 origin "$POB_COMMIT"
git checkout --quiet "$POB_COMMIT"
echo "Path of Building @ $(git rev-parse --short HEAD) → $DEST"
echo
echo "Add to backend/.env:"
echo "  RECKONER_POB_SRC=$DEST/src"
echo "  RECKONER_POB_SOURCE_COMMIT=$(git rev-parse HEAD)"
