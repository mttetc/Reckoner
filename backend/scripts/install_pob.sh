#!/usr/bin/env sh
# Install a pinned Path of Building checkout for the headless engine (SPEC § 5 B).
#
#   backend/scripts/install_pob.sh [DEST]      default DEST: <repo>/.engines/pob
#
# Requires git and luajit (`brew install luajit` / `apt install luajit`). The checkout is sparse:
# tree sprite PNGs are excluded (≈340 MB) — headless PoB stubs image loading and never reads them.
# Bump POB_COMMIT deliberately: the engine version ends up in every recalculated metric's provenance.
set -eu

# Preflight: PoB's sources use compound assignment (`x += 1`), accepted only by LuaJIT rolling
# builds from mid-2026 on (Homebrew is fine; Debian/Ubuntu packages are not — build from source,
# see .github/workflows/ci.yml for the exact commit).
LUAJIT="${LUAJIT_BIN:-luajit}"
if ! command -v "$LUAJIT" >/dev/null 2>&1; then
  echo "error: '$LUAJIT' not found. brew install luajit, or build https://github.com/LuaJIT/LuaJIT" >&2
  exit 1
fi
if ! "$LUAJIT" -e 'local c = 0; c += 1' >/dev/null 2>&1; then
  echo "error: $("$LUAJIT" -v 2>&1 | head -1) is too old for Path of Building (no compound assignment)." >&2
  echo "       Build LuaJIT from source at a 2026 commit; see .github/workflows/ci.yml (LUAJIT_COMMIT)." >&2
  exit 1
fi

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
