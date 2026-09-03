"""Number audit: every number in the answer must be traceable to a tool result.

We do not trust the model to only quote tool numbers; we check. Tool results are serialised and
every numeric token in them (plus rounded / compact variants of floats) becomes an allowed value.
Each numeric token in the answer must match one within a small relative tolerance. What does not
match is reported as ``unverified`` — shown to the user, never silently accepted.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

# A number: optional thousands groups, optional decimals, optional k/M/B or % suffix. Not glued to
# a word or to a further ".digit" ("3.29.0b" is left alone; "3.27." at a sentence end counts).
_NUM_IN_ANSWER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,](\d+))?\s*([kKmMbB]|%)?(?!\w)(?!\.\d)"
)
_NUM_IN_RESULTS = re.compile(r"-?\d+(?:\.\d+)?")
_LIST_MARKER = re.compile(r"(?m)^[ \t]*\d{1,2}[.)](?=\s)")
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}
_IGNORE_BELOW = 0  # audit everything; small integers are as inventable as large ones


@dataclass
class Audit:
    checked: int = 0
    unverified: list[str] = field(default_factory=list)
    allowed_count: int = 0

    @property
    def clean(self) -> bool:
        return not self.unverified


def allowed_values(results: list[Any]) -> set[float]:
    text = json.dumps(results, default=str)
    vals: set[float] = set()
    for tok in _NUM_IN_RESULTS.findall(text):
        try:
            v = float(tok)
        except ValueError:
            continue
        if not math.isfinite(v):
            continue
        vals.add(v)
        vals.add(abs(v))
        # version-like tokens (3.29) are also allowed as their parts (3, 29)
    # digits inside version strings like "3.29.0b" or ids are matched by the regex above already
    return vals


def _parse_answer_number(int_part: str, frac: str | None, suffix: str | None) -> tuple[float, bool]:
    """Returns (value, is_percent). '18 619 973,8' (fr) and '18,619,973.8' (en) both work."""
    digits = int_part.replace(" ", "").replace(",", "")
    value = float(digits + ("." + frac if frac else ""))
    if suffix and suffix.lower() in _SUFFIX:
        return value * _SUFFIX[suffix.lower()], False
    return value, suffix == "%"


def _matches(value: float, allowed: set[float], compact: bool) -> bool:
    if value in allowed:
        return True
    tol = 0.006 if compact else 0.0005  # "18.6M" vs 18,619,973.8 ; "3,120" vs 3120.0
    for a in allowed:
        if a == 0:
            if abs(value) < 1e-9:
                return True
            continue
        if abs(value - a) / abs(a) <= tol:
            return True
        # Answers may round large values to fewer decimals (3120.4 → 3,120). Small numbers must
        # match tightly: 3.30 is not a rounding of patch 3.29, it is another patch.
        if abs(a) >= 100 and (abs(value - round(a, 1)) < 1e-9 or abs(value - round(a)) < 1e-9):
            return True
    return False


def audit_answer(answer: str, results: list[Any], question: str | None = None) -> Audit:
    allowed = allowed_values(results)
    if question:
        # Numbers the user wrote ("PoE 2", "under 20 divines") may be echoed back.
        allowed |= allowed_values([question])
    audit = Audit(allowed_count=len(allowed))
    for m in _NUM_IN_ANSWER.finditer(answer):
        if _LIST_MARKER.match(answer, m.start()):
            continue  # "2." / "3)" opening a line is list numbering, not a claim
        int_part, frac, suffix = m.group(1), m.group(2), m.group(3)
        # "3.29" style tokens: the regex captures int=3 frac=29 → value 3.29 — fine, results
        # contain "3.29" when a patch was quoted.
        value, _is_pct = _parse_answer_number(int_part, frac, suffix)
        audit.checked += 1
        if not _matches(value, allowed, compact=bool(suffix and suffix.lower() in _SUFFIX)):
            audit.unverified.append(m.group(0).strip())
    return audit
