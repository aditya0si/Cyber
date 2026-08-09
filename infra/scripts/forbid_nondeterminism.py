"""
Determinism guard (see docs/07 §1.1, docs/04 §3 rule #5, docs/21 Task 0.1).

Forbids the use of non-deterministic primitives OUTSIDE sanctioned files:
  - random.random(), random.uniform, random.randint, random.choice, random.seed, ...
  - time.time(), time.monotonic() used for *seeding* (cooperative sim clock is fine)
  - uuid.uuid4() / uuid.uuid1()

Sanctioned homes:
  cybersim/simulation/core/rng.py        — SeededRNG wrapping a deterministic generator
  cybersim/simulation/core/clock.py      — SimClock deterministic sim-time
  cybersim/infra/uuidv7.py               — deterministic UUIDv7 minted from clock + rng

Test files are exempt (their generators may use python random freely).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = {
    r"\brandom\.(random|uniform|randint|choice|sample|seed|gauss|shuffle|randrange|choices)\s*\(",
    r"\buuid\.uuid4\s*\(",
    r"\buuid\.uuid1\s*\(",
    r"\btime\.time\s*\(",
    r"\btime\.monotonic\s*\(",
}

SANCTIONED = {
    Path("cybersim/simulation/core/rng.py"),
    Path("cybersim/simulation/core/clock.py"),
    Path("cybersim/infra/uuidv7.py"),
    Path("cybersim/tools/seed_knowledge.py"),
}

# Files that legitimately use time/datetime non-deterministically for *bookkeeping*
# (audit logs, telemetry) are allowed *time.time()* but never *random.* / *uuid.{1,4}*.
ALLOW_TIME_BOOKKEEPING = {
    "cybersim/infra/logging/",
    "cybersim/infra/telemetry/",
    "cybersim/api/",
    "cybersim/realtime/",
    "cybersim/platform/billing/",
    "cybersim/tools/",
    # middleware bookkeeping: idempotency TTL + rate-limit windows
    "cybersim/infra/middleware/idempotency.py",
    "cybersim/infra/middleware/rate_limit.py",
}

# Files that legitimately mint *uuid.uuid4()* for bookkeeping ids (DB rows,
# sessions, idempotency keys) — the determinism rule applies to SIMULATION
# event ids only (docs/07 §1.2, docs/00 §3 rule #4). time.time() here is
# allowed too (TTL/rate-limit bookkeeping).
ALLOW_UUID_BOOKKEEPING = {
    "cybersim/platform/auth/repo.py",
    "cybersim/platform/simulation/store.py",
    "cybersim/infra/middleware/idempotency.py",
    "cybersim/infra/middleware/rate_limit.py",
    "cybersim/response/executor.py",
}


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for arg in argv:
        p = Path(arg)
        if not p.exists() or not p.is_file():
            continue
        rel = p.as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel_path = Path(rel)
        # sanctioned files skip fully
        if rel_path in SANCTIONED or any(
            rel.startswith(prefix) for prefix in ALLOW_TIME_BOOKKEEPING
        ):
            continue
        is_uuid_allowed = rel in ALLOW_UUID_BOOKKEEPING
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in FORBIDDEN_PATTERNS:
                if is_uuid_allowed and "uuid" in pat:
                    continue
                if re.search(pat, line):
                    failures.append(f"{rel}:{lineno}: {line.strip()}")
    if failures:
        sys.stderr.write(
            "Forbidden non-deterministic primitive(s) found (see docs/07 §1.1):\n  "
            + "\n  ".join(failures)
            + "\n\nUse cybersim.simulation.core.rng.SeededRNG / cybersim.infra.uuidv7 "
            "instead.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
