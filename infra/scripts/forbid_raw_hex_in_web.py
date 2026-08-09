"""
Design-token guard (see docs/02 §8).

Forbids raw hex literals (#......) inside apps/web/src/ component code except
within the sanctioned files where the design system defines tokens:
  apps/web/src/styles/tokens.css
  apps/web/src/styles/animations.css
  apps/web/tailwind.config.ts

Code outside those should consume --cs-* CSS variables via utility classes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b")

SANCTIONED = {
    "apps/web/src/styles/tokens.css",
    "apps/web/src/styles/animations.css",
    "apps/web/tailwind.config.ts",
}


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for arg in argv:
        p = Path(arg)
        rel = p.as_posix()
        if rel in SANCTIONED:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if HEX_RE.search(line):
                failures.append(f"{rel}:{lineno}: {line.strip()}")
    if failures:
        sys.stderr.write(
            "Raw hex literal(s) found in web source (see docs/02 §8):\n  "
            + "\n  ".join(failures)
            + "\n\nUse --cs-* design tokens via utility classes instead.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
