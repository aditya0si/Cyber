"""KnowledgeEntry model (docs/12 §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeEntry:
    """A single retrievable knowledge chunk (docs/12 §3.1)."""

    entry_id: str
    org_id: str = "global"
    source: str = "cms_notes"  # mitre|owasp|cve|cwe|cms_notes
    source_id: str = ""
    kind: str = "article"  # technique|tactic|weakness|vuln|article
    title: str = ""
    summary: str = ""
    content: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    language: str = "en"
    tags: tuple[str, ...] = ()

    @property
    def display_id(self) -> str:
        """E.g. 'mitre:T1110' or 'owasp:A03:2021'."""
        return f"{self.source}:{self.source_id}" if self.source_id else self.entry_id
