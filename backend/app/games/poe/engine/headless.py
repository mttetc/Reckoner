"""Client for ``bridge.lua``: a persistent LuaJIT process running Path of Building headless.

One process, one build at a time, requests serialised by a lock. Every ``recalculate`` call
starts from a fresh ``load`` so state never leaks between requests. Any failure to start or answer
surfaces as ``EngineUnavailable``; anything PoB refuses surfaces as ``InvalidModification``.
"""

from __future__ import annotations

import collections
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings
from app.domain.errors import EngineUnavailable, InvalidModification

_HERE = Path(__file__).resolve().parent
BRIDGE = _HERE / "bridge.lua"
SHIM_DIR = _HERE / "shim"


@dataclass(frozen=True)
class EngineInfo:
    engine: str
    engine_version: str | None
    latest_tree_version: str | None
    source_commit: str | None
    modification_kinds: tuple[str, ...]


@dataclass(frozen=True)
class EngineStats:
    player: dict[str, float]
    minion: dict[str, float]
    main_skill: str | None
    tree_version: str | None
    allocated_nodes: int
    class_name: str | None
    ascend_class_name: str | None


@dataclass(frozen=True)
class ModifyResult:
    stats: EngineStats
    xml: str
    applied: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def _numbers(v: Any) -> dict[str, float]:
    # dkjson encodes an empty Lua table as [] — treat that as "no rows".
    return {k: float(x) for k, x in v.items()} if isinstance(v, dict) else {}


def _stats(raw: dict[str, Any]) -> EngineStats:
    return EngineStats(
        player=_numbers(raw.get("player")),
        minion=_numbers(raw.get("minion")),
        main_skill=raw.get("main_skill"),
        tree_version=raw.get("tree_version"),
        allocated_nodes=int(raw.get("allocated_nodes") or 0),
        class_name=raw.get("class_name"),
        ascend_class_name=raw.get("ascend_class_name"),
    )


_FROM_SETTINGS: Any = object()  # sentinel: "take the value from settings"


class PobHeadless:
    def __init__(
        self,
        pob_src: Path | str | None = _FROM_SETTINGS,
        luajit_bin: str | None = None,
        timeout_s: float | None = None,
        source_commit: str | None = None,
    ) -> None:
        # Passing pob_src=None explicitly means "no engine", used to test degraded behaviour.
        src = settings.pob_src if pob_src is _FROM_SETTINGS else pob_src
        self.pob_src = Path(src) if src else None
        self.luajit_bin = luajit_bin or settings.luajit_bin
        self.timeout_s = timeout_s or settings.engine_timeout_s
        self.source_commit = source_commit or settings.pob_source_commit
        self._proc: subprocess.Popen[str] | None = None
        self._info: EngineInfo | None = None
        self._stderr: collections.deque[str] = collections.deque(maxlen=40)
        self._trees: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._next_id = 0

    # ------------------------------------------------------------------ availability

    @property
    def configured(self) -> bool:
        return self.pob_src is not None

    def available(self) -> bool:
        """Cheap, no process spawn: is there something to run?"""
        return (
            self.pob_src is not None
            and (self.pob_src / "HeadlessWrapper.lua").is_file()
            and shutil.which(self.luajit_bin) is not None
        )

    def unavailable_reason(self) -> str:
        if self.pob_src is None:
            return "RECKONER_POB_SRC is not set; see backend/scripts/install_pob.sh"
        if not (self.pob_src / "HeadlessWrapper.lua").is_file():
            return f"{self.pob_src} is not a Path of Building src/ directory"
        if shutil.which(self.luajit_bin) is None:
            return f"'{self.luajit_bin}' not found on PATH"
        return "engine process failed"

    # ------------------------------------------------------------------ process

    def _start(self) -> None:
        if not self.available():
            raise EngineUnavailable(self.unavailable_reason())
        assert self.pob_src is not None
        env = dict(os.environ)
        env["LUA_PATH"] = ";".join(
            [
                f"{SHIM_DIR}/?.lua",
                "./?.lua",
                "../runtime/lua/?.lua",
                "../runtime/lua/?/init.lua",
                ";",  # keep LuaJIT defaults
            ]
        )
        if self.source_commit:
            env["POB_SOURCE_COMMIT"] = self.source_commit
        try:
            self._proc = subprocess.Popen(
                [self.luajit_bin, str(BRIDGE)],
                cwd=self.pob_src,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise EngineUnavailable(f"cannot start {self.luajit_bin}: {exc}") from exc
        self._stderr.clear()
        threading.Thread(target=self._drain_stderr, args=(self._proc,), daemon=True).start()
        ready = self._readline()
        if not ready or ready.get("event") != "ready":
            self._kill()
            raise EngineUnavailable(
                "engine did not become ready. PoB stderr tail:\n" + self.stderr_tail()
            )
        info = ready.get("info") or {}
        self._info = EngineInfo(
            engine=info.get("engine") or "Path of Building",
            engine_version=info.get("engine_version"),
            latest_tree_version=info.get("latest_tree_version"),
            source_commit=info.get("source_commit") or self.source_commit,
            modification_kinds=tuple(info.get("modification_kinds") or ()),
        )

    def _drain_stderr(self, proc: subprocess.Popen[str]) -> None:
        # PoB logs progress (and startup errors) on stderr; keep the tail for diagnostics.
        assert proc.stderr is not None
        for line in proc.stderr:
            self._stderr.append(line.rstrip("\n"))

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr)

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass
        self._proc = None
        self._info = None

    def _readline(self) -> dict[str, Any] | None:
        assert self._proc is not None and self._proc.stdout is not None
        result: dict[str, Any] = {}

        def read() -> None:
            line = self._proc.stdout.readline()  # type: ignore[union-attr]
            result["line"] = line

        t = threading.Thread(target=read, daemon=True)
        t.start()
        t.join(self.timeout_s)
        if t.is_alive():
            self._kill()
            raise EngineUnavailable(f"engine did not answer within {self.timeout_s:.0f}s")
        line = result.get("line") or ""
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise EngineUnavailable(f"engine sent malformed output: {line[:120]!r}") from exc

    def _request(self, op: str, **payload: Any) -> Any:
        """Send one request; must be called with the lock held."""
        if self._proc is None or self._proc.poll() is not None:
            self._start()
        assert self._proc is not None and self._proc.stdin is not None
        self._next_id += 1
        req = {"id": self._next_id, "op": op, **payload}
        try:
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._kill()
            raise EngineUnavailable("engine process died") from exc
        resp = self._readline()
        if resp is None:
            self._kill()
            raise EngineUnavailable("engine closed its output")
        if not resp.get("ok"):
            raise InvalidModification(str(resp.get("error")))
        return resp.get("result")

    # ------------------------------------------------------------------ public API

    def info(self) -> EngineInfo:
        with self._lock:
            if self._info is None:
                self._start()
            assert self._info is not None
            return self._info

    def evaluate(self, xml: str) -> tuple[EngineInfo, EngineStats]:
        """Load an XML build and return PoB's numbers for it, untouched."""
        with self._lock:
            raw = self._request("load", xml=xml)
            assert self._info is not None
            return self._info, _stats(raw)

    def evaluate_modified(
        self, xml: str, modifications: list[dict[str, Any]]
    ) -> tuple[EngineInfo, EngineStats, ModifyResult]:
        """Fresh load, then apply modifications and recompute. Returns baseline and variant."""
        with self._lock:
            base = _stats(self._request("load", xml=xml))
            raw = self._request("modify", modifications=modifications)
            assert self._info is not None
            return (
                self._info,
                base,
                ModifyResult(
                    stats=_stats(raw["stats"]),
                    xml=raw["xml"],
                    applied=tuple(raw.get("applied") or ()),
                ),
            )

    def tree_geometry(self, version: str) -> dict[str, Any]:
        """Node positions and links of a tree version, computed by PoB. Cached per version."""
        key = version.replace(".", "_")
        with self._lock:
            cached = self._trees.get(key)
            if cached is not None:
                return cached
            data = self._request("tree", version=key)
            self._trees[key] = data
            return data

    def close(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._request("quit")
                except Exception:
                    pass
            self._kill()


_engine: PobHeadless | None = None
_engine_lock = threading.Lock()


def get_engine() -> PobHeadless:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = PobHeadless()
        return _engine
