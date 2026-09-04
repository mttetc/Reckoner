#!/usr/bin/env sh
# Build a pinned SimulationCraft CLI (no GUI) for the World of Warcraft Retail engine.
#
#   backend/scripts/install_simc.sh [DEST]      default DEST: <repo>/.engines/simc
#
# Requires git, cmake and a C++20 compiler. The resulting binary is DEST/build/simc; point
# RECKONER_SIMC_BIN at it. Bump SIMC_COMMIT deliberately: SimulationCraft's version and the game
# build it carries end up in every simulated metric's provenance.
set -eu

SIMC_REPO="https://github.com/simulationcraft/simc.git"
SIMC_COMMIT="${SIMC_COMMIT:-b9880014fd36e63d301b8c7fe9a93c5a66f1a82f}"   # midnight branch, 12.1.0, 2026-09-03
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-$ROOT/.engines/simc}"

for tool in git cmake; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: '$tool' not found" >&2
    exit 1
  fi
done

if [ -x "$DEST/build/simc" ] && [ "$(git -C "$DEST" rev-parse HEAD 2>/dev/null)" = "$SIMC_COMMIT" ]; then
  echo "SimulationCraft already built at $DEST/build/simc ($SIMC_COMMIT)"
  exit 0
fi

if [ ! -d "$DEST/.git" ]; then
  git clone --quiet --filter=blob:none "$SIMC_REPO" "$DEST"
fi
git -C "$DEST" fetch --quiet origin "$SIMC_COMMIT"
git -C "$DEST" checkout --quiet "$SIMC_COMMIT"

cmake -S "$DEST" -B "$DEST/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_GUI=OFF >/dev/null
cmake --build "$DEST/build" --target simc -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
"$DEST/build/simc" 2>/dev/null | head -1 || true
echo "SimulationCraft built at $DEST/build/simc"
