"""Analyst prompt templates (docs/11 §6)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

_env = Environment(
    loader=FileSystemLoader(str(_PROMPT_DIR)),
    undefined=StrictUndefined,
    autoescape=False,
)


def render(template_name: str, **ctx: object) -> str:
    """Render a Jinja2 prompt template with strict undefined vars."""
    return _env.get_template(template_name).render(**ctx)


__all__ = ["render"]
