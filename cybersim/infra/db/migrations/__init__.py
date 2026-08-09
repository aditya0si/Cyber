"""Alembic migrations package (docs/09 §11)."""

import sys
from pathlib import Path

# Ensure `cybersim.*` is importable from Alembic's autogenerate.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
