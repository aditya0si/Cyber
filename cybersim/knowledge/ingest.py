"""Knowledge ingestion adapters (docs/12 §3).

All ingest is OFFLINE — reads vendored fixtures / catalog files; no network.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from cybersim.knowledge.entries import KnowledgeEntry

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "knowledge"


def ingest_mitre(path: Path | None = None) -> list[KnowledgeEntry]:
    """Parse the MITRE ATT&CK fixture (docs/12 §3.2)."""
    p = path or FIXTURE_DIR / "mitre_sample.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    out: list[KnowledgeEntry] = []
    for tech in data.get("techniques", []):
        tid = tech["id"]
        out.append(
            KnowledgeEntry(
                entry_id=f"mitre:{tid}",
                source="mitre",
                source_id=tid,
                kind="technique",
                title=tech["name"],
                summary=f"MITRE ATT&CK technique {tid}: {tech['name']}",
                content=(
                    f"{tech['name']} ({tid}). {tech['description']} "
                    f"Detection: {tech.get('detection', '')} "
                    f"Mitigation: {tech.get('mitigation', '')}"
                ),
                payload={"tactics": tech.get("tactic_ids", [])},
                tags=tuple(tech.get("tags", [tid])),
            )
        )
    return out


def ingest_owasp(path: Path | None = None) -> list[KnowledgeEntry]:
    """Parse the OWASP Top-10 markdown fixture."""
    p = path or FIXTURE_DIR / "owasp_sample.md"
    text = p.read_text(encoding="utf-8")
    out: list[KnowledgeEntry] = []
    for section in re.split(r"^## ", text, flags=re.M)[1:]:
        title_line, _, body = section.partition("\n")
        title = title_line.strip()
        m = re.match(r"(A\d{2}:\d{4})", title)
        sid = m.group(1) if m else title
        tags = re.findall(r"tags: (.+)", body)
        tag_tuple = tuple(t.strip() for t in (tags[0].split(",") if tags else []))
        out.append(
            KnowledgeEntry(
                entry_id=f"owasp:{sid}",
                source="owasp",
                source_id=sid,
                kind="weakness",
                title=title,
                summary=f"OWASP {sid}: {title.split('—')[0]}",
                content=body.strip(),
                tags=tag_tuple,
            )
        )
    return out


def ingest_cve(path: Path | None = None) -> list[KnowledgeEntry]:
    """Parse the CVE fixture slice."""
    p = path or FIXTURE_DIR / "cve_sample.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    out: list[KnowledgeEntry] = []
    for cve in data:
        cid = cve["id"]
        out.append(
            KnowledgeEntry(
                entry_id=f"cve:{cid}",
                source="cve",
                source_id=cid,
                kind="vuln",
                title=f"CVE {cid}",
                summary=cve["description"][:160],
                content=cve["description"],
                payload={"cvss": cve.get("cvss"), "cwe": cve.get("cwe", [])},
                tags=tuple(f"CWE-{w}" for w in cve.get("cwe", [])) or (),
            )
        )
    return out


def ingest_all() -> list[KnowledgeEntry]:
    """All default knowledge slices (used by seed CLI + tests)."""
    return [*ingest_mitre(), *ingest_owasp(), *ingest_cve()]


def load_fixture_entries() -> Iterable[KnowledgeEntry]:
    return ingest_all()
