# 06 — PPTX Deck Build (Actual Competition Template)

Depends on: `00-overview.md` and ideally `01`–`05` complete or near-complete
so real screenshots and real numbers exist to put in the deck.

Template file: `Shortlisting_PPT_Template__Round_1_.pptx`
Max slides: 9 (per official rules) — **the actual template provided has 6
content slides + 1 guidelines slide to delete before submission.** Do not
assume a generic 9-slide structure; use the real template layouts below.

---

## Actual template structure (verified)

| # | Layout name | Fields present |
|---|---|---|
| 1 | Title | Theme, Idea Title, Team Name (registered on portal) |
| 2 | Idea Title | Proposed Solution, Detailed explanation, How it addresses the problem, Innovation and uniqueness |
| 3 | Technical Approach | Two columns: Technologies (languages/frameworks/hardware) \| Methodology (process, flow charts, images, working prototype) |
| 4 | Feasibility and Viability | Three cards: Feasibility, Challenges, Strategies |
| 5 | Impact and Benefits | Potential impact on target audience, Benefits (social/economic/environmental) |
| 6 | Research and References | Links/details of reference and research work |
| 7 | Guidelines (delete before submission) | — |

This is fewer slides than a generic pitch deck template, so **do not spread
content thin trying to fill 9 slides** — use the 6 given slides well.
Screenshots of the prototype live inside slide 3 (Methodology / working
prototype), there is no separate dedicated screenshots slide.

---

## Content, slide by slide

### Slide 1 — Title
- Theme: **Cybersecurity & Digital Sovereignty**
- Idea Title: **CyberSim AI**
- Team Name: [as registered on the Unstop portal — must match exactly]

### Slide 2 — Idea Title (this is really "Problem + Solution")

**Proposed Solution (one line):**
> An evidence-grounded AI cyber defense simulator that models attack
> progression as a live graph and recommends defensive actions, with a
> human in the loop before any action executes.

**Detailed explanation:**
Use the sharper framing, not a generic "SOC alerts overwhelm analysts"
line:

> Security tools detect individual events — a failed login, a privilege
> change, a database query — as separate alerts. But a real attack isn't a
> pile of isolated alerts, it's an evolving path: brute force → account
> compromise → privilege escalation → database access. CyberSim AI
> reconstructs that path as a live attack graph and uses a LangGraph-based
> AI analyst to reason across the graph, cite evidence from MITRE ATT&CK
> and OWASP, and recommend a response — which a human then approves before
> it's simulated in the environment.

**How it addresses the problem:**
- Reconstructs multi-stage attacks as a single connected path instead of N
  disconnected alerts
- Grounds every AI judgment in retrieved security evidence, not
  unsupported LLM assertion
- Keeps a human in the loop for any action — a defensible design for a
  security tool, not autonomous action

**Innovation and uniqueness:**
- Attack-path reasoning via a live graph, not alert-list triage
- Evidence-grounded (RAG-backed) AI explanations with cited sources
- Closed loop: observe → reason → decide → human-approve → act → observe
  again — a genuinely agentic workflow, not a single LLM call

### Slide 3 — Technical Approach

**Technologies column:**
```
Frontend: React, TypeScript, Tailwind, React Flow
Backend: Python 3.11, FastAPI
AI: LangGraph, rule-based reasoning core with optional LLM enhancement
Graph: NetworkX (abstracted for future Neo4j)
Knowledge: sentence-transformers (all-MiniLM-L6-v2), TF-IDF fallback
```

**Methodology column:**
The pipeline diagram (build as a clean flowchart, not a screenshot of ASCII
art):
```
Simulated Attack → Event Engine → Attack Graph → LangGraph AI Analyst
  → Human-Approved Response → Simulated Containment
```
Plus a compressed version of the LangGraph node sequence from `00` Section
7. If real screenshots from `05` exist by build time, include 1-2 small
ones here (event stream + threat card, or graph + threat card) — this is
the template's designated spot for "working prototype" evidence.

### Slide 4 — Feasibility and Viability

**Feasibility:**
> Core pipeline (simulation → event engine → attack graph → LangGraph
> analyst → response) is implemented and runs fully offline with a
> rule-based reasoning core — no dependency on external APIs for the demo.

**Challenges:**
> Real-time graph rendering at low latency; keeping AI reasoning
> explainable and evidence-grounded rather than a black box; scoping a
> convincing MVP without building a full multi-simulator platform in the
> available time.

**Strategies:**
> NetworkX for a fast, dependency-light graph layer with production-Neo4j
> path already abstracted; rule-based reasoning nodes as the reliable
> default with optional LLM enhancement behind a flag; deliberate Round 1
> scope limited to one attack chain, with additional simulators
> (network, cloud, supply-chain) planned as the same architecture extended,
> not rebuilt.

### Slide 5 — Impact and Benefits

**Target audience / potential impact:**
- SOC teams and security analysts — faster, path-level triage instead of
  alert-by-alert fatigue
- Universities and cybersecurity training programs — a safe, controlled
  environment to teach attack progression and response reasoning
- Security researchers — a testbed for evaluating AI-assisted detection
  and response logic
- SMEs without a mature SOC — an accessible, explainable first line of
  automated reasoning

**Benefits:**
- Faster understanding of multi-stage attacks vs. manual log correlation
- Explainable, evidence-cited AI output — auditable, not a black box
- Human-approved response model — safer default for real security
  operations than autonomous action
- Extensible architecture — new attack domains plug into the same event/
  graph/AI layers

### Slide 6 — Research and References

List actual sources used for the RAG corpus and design grounding:
- MITRE ATT&CK — Brute Force (T1110): [URL]
- MITRE ATT&CK — Valid Accounts (T1078): [URL]
- OWASP — relevant authentication/credential attack references: [URL]
- LangGraph documentation: [URL]
- (Any additional sources actually used in `03`'s corpus — list the real
  ones, don't pad this list with sources not actually referenced.)

### Delete slide 7 (Guidelines) before final export.

---

## Build process

1. Use the pptx skill (`/mnt/skills/public/pptx/SKILL.md`) — this is an
   edit-existing-template task, not a from-scratch build.
2. Thumbnail the template first to confirm layout numbering hasn't shifted
   if the file has been touched: `python scripts/thumbnail.py
   template.pptx template-thumbs`
3. Unzip, edit `ppt/slides/slideN.xml` directly for each of the 6 content
   slides using the content above. Preserve the template's existing
   formatting, color scheme, and fonts — the rules explicitly say "follow
   the color scheme for slides."
4. Delete the Guidelines slide (slide 7) from `<p:sldIdLst>` before final
   packaging, then run `clean.py` to remove orphaned parts.
5. If screenshots from the working prototype (`05`) are ready, insert them
   on slide 3 at reasonable size — do not stretch/distort, do not let them
   overflow the layout's content area.
6. Run required QA per the pptx skill:
   - `markitdown output.pptx` — check for missing content, typos,
     leftover placeholder text (grep for `lorem`, `TODO`, `[insert`, etc.)
   - `python scripts/office/validate.py output.pptx --original
     Shortlisting_PPT_Template__Round_1_.pptx`
   - Convert to images and visually inspect every slide for overflow,
     overlap, and template decoration misalignment (per the skill's visual
     QA checklist)
7. Confirm final slide count is ≤ 9 (should be 6 here) and matches the
   required template exactly, with team name matching the Unstop portal
   registration exactly.

---

## AI-use disclosure reminder

Per the competition rules and `00` Section 9: if the guidelines require an
AI-use declaration, note that AI tools were used for ideation, drafting
assistance, and code scaffolding support, with all engineering decisions
reviewed and understood by the team. Do not claim the project was built
without AI assistance if it wasn't — misrepresenting this risks
disqualification and defeats the purpose of the disclosure requirement.

---

## Checkpoint — what should exist at the end of this file

A submittable `.pptx`: 6 content slides matching the real template exactly,
correct team name, real (not placeholder) content throughout, at least one
real prototype screenshot if `05` finished in time, passing all three QA
steps above, Guidelines slide removed.

---

## You must be able to explain

- Why the "meaningful unit is the attack path, not the alert" framing is
  the core pitch, and be able to defend it against "isn't this just log
  correlation" from a skeptical judge
- Every technology listed on the Technical Approach slide — what it's
  used for, specifically, not just that it appears in the stack table
- The actual Round 1 → Round 2 strategic reasoning (Cybersecurity theme
  chosen deliberately, understanding what that means for Round 2 problem
  statement flexibility)
