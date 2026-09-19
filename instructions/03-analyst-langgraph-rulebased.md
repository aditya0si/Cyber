# 03 — LangGraph AI Analyst (Rule-Based Primary, LLM Optional) + RAG

Depends on: `00-overview.md`, `01-simulator-and-events.md`, `02-attack-graph.md`.

Target repo path (audit first per `00` Section 3): `cybersim/analyst/`,
`cybersim/knowledge/`

**This is the centerpiece of the whole project. Spend your best engineering
time here.**

---

## Goal of this stage

At the end of this file, feeding the completed `01` event sequence through
this pipeline produces a threat card (severity, confidence, evidence,
attack path, recommended response) **with zero API calls**, using only
rule-based logic and the local graph/RAG lookups. If an LLM key is added
later, the same pipeline produces richer natural-language explanations
without changing its structure.

---

## Step 1 — Audit

1. Read `cybersim/analyst/` fully — is there existing LangGraph wiring? Rule
   based fallbacks? Validation logic (the teammate's summary mentions
   "rule-based fallbacks and validations" already existing — verify this is
   real and not aspirational).
2. Read `cybersim/knowledge/` — is there already a RAG setup? What
   embedding approach, if any? What corpus, if any?
3. Record decisions in `AUDIT.md`.

---

## Step 2 — The node sequence (do not deviate)

Per `00` Section 7:

```
START → Event Aggregator → Threat Detector → Attack Graph Retriever
  → Evidence Retriever (RAG) → Threat Analyst → Risk Assessor
  → Response Planner → Human Approval → Simulation Action
  → Environment Updated → END / Re-evaluate
```

Each node is a LangGraph node with a clear single responsibility. Build each
node with **two implementations behind a common interface**: a rule-based
version (default, always available) and an LLM-enhanced version (used only
if `USE_LLM=true` and a key is configured). The state object passed between
nodes should be identical either way — the LLM path only enriches specific
fields (mainly natural-language explanation text), it never changes what
data is available downstream.

### Node specs

**Event Aggregator**
- Input: recent events from the Event Engine log (`01`)
- Output: a windowed summary — counts by type, time span, involved
  actors/assets
- Rule-based: simple aggregation/counting, no LLM needed ever — this node
  has no LLM variant, it's pure data prep

**Threat Detector**
- Input: aggregated events
- Output: boolean/score — "is this pattern suspicious," which pattern
- Rule-based: threshold logic, e.g. `failed_login_count >= 5 AND
  followed_by_success == True` → flag `credential_brute_force`. Define 2-3
  such rules covering the scenario's stages (brute force, priv-esc pattern,
  suspicious DB access following compromise).
- LLM variant: optional, only if you want the LLM to also catch patterns
  the rules miss — not required for Round 1, skip unless there's spare time

**Attack Graph Retriever**
- Input: flagged threat + graph reference
- Output: attack path, reachable critical assets (calls the methods
  defined in `02` Step 6)
- No LLM needed — pure graph query

**Evidence Retriever (RAG)**
- Input: the detected threat category (e.g. `credential_brute_force`)
- Output: top-k relevant excerpts from the local corpus
- See Step 3 below for the full RAG spec

**Threat Analyst**
- Input: threat category, aggregated events, attack path, RAG evidence
- Output: structured threat assessment — category, severity, human-readable
  explanation, cited evidence
- Rule-based: template-based explanation generation. Build 2-3 well-written
  templates keyed to the threat categories from Threat Detector, filled
  with the actual event counts/asset names/evidence text. Should not read
  as an obvious mad-lib — invest time in template wording quality since
  this is the text judges will actually read.
- LLM variant (optional): given the same structured inputs, produce a
  fluent explanation. Must still cite the same evidence sources.

**Risk Assessor**
- Input: threat assessment + reachable critical assets from the graph
- Output: severity (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`) and a confidence score
- Rule-based: deterministic scoring function, e.g. weighted sum of (event
  severity escalation, number of critical assets reachable, whether DB
  access already occurred). Document the formula — "confidence: 91%" must
  come from an actual calculation you can explain, not a fabricated number.

**Response Planner**
- Input: threat assessment + severity
- Output: ordered list of recommended actions with a one-line reason for
  each, e.g.:
  ```
  1. Isolate compromised account — prevents further lateral movement
  2. Revoke active sessions — closes existing access
  3. Rotate credentials — invalidates leaked/guessed credentials
  4. Investigate database access — confirms scope of exposure
  ```
- Rule-based: a lookup table keyed by threat category → ordered action list
  with reasons. Small and explicit, not generated.

**Human Approval**
- This is a **UI-blocking step, not a LangGraph auto-continue**. The graph
  pauses here; the dashboard shows the recommended response and an
  `EXECUTE RESPONSE` button. Only a real click resumes the graph.
  Implementation-wise: the backend can expose
  `POST /analyst/approve-response` which resumes/continues the LangGraph
  run (or triggers the next stage if you're not persisting LangGraph state
  across the HTTP boundary — see note below).
- **Note on state**: if keeping a LangGraph run suspended across an HTTP
  request is awkward, an acceptable simplification is: run
  Event Aggregator → ... → Response Planner as one pipeline call that
  returns the recommendation, and treat "Human Approval → Simulation
  Action → Environment Updated" as a second pipeline call triggered by the
  approval endpoint. The conceptual pipeline is unchanged; only the
  execution mechanics are pragmatic. Note this simplification in `AUDIT.md`
  so it can be explained honestly if asked.

**Simulation Action**
- Input: approved response actions
- Output: calls the graph mutation methods from `02` Step 5, and
  optionally emits new synthetic events (e.g. `ACCOUNT_ISOLATED`) so the
  Event Stream panel shows the containment happening too

**Environment Updated / Re-evaluate**
- Confirms graph and event state now reflect containment
- Optionally: re-run Threat Detector on the new state to show status
  flipping to `CONTAINED` — this closes the observe-reason-decide-act-observe
  loop and is worth the extra effort if time allows

---

## Step 3 — RAG spec

**Corpus:** small and scoped. 5-10 short excerpts total, covering only:
- MITRE ATT&CK: Brute Force (T1110) and Valid Accounts (T1078) — summarized
  in your own words, a few sentences each, sourced from the public MITRE
  ATT&CK site
- OWASP: relevant excerpts on authentication/credential attacks, similarly
  summarized
- 1-2 short remediation notes (can be written by you, don't need to be from
  an external source, as long as they're accurate)

Store each as a small JSON/YAML record: `{id, title, source_url, category,
text}`. Keep `source_url` so the dashboard can show "Source: MITRE ATT&CK
T1110" as a citation, which materially increases how credible the AI output
looks to judges.

**Embedding approach (per your explicit spec):**

```python
# Primary path
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # downloaded once at setup
# embed corpus once at startup, cache in memory
# embed query (threat category description), cosine similarity, top-k
```

```python
# Fallback path — used automatically if the model can't load
# (no internet on setup day, download failed, etc.)
from sklearn.feature_extraction.text import TfidfVectorizer
# fit on corpus at startup, transform query, cosine similarity, top-k
```

Implementation requirement: **the RAG module must detect at startup whether
the embedding model loaded successfully and silently use the TF-IDF
fallback if not** — no crash, no demo-day dependency on model download
succeeding live. Log which mode is active so you know which one ran during
any given demo/test, but don't surface this as a warning in the UI (it's
an implementation, not a judge-facing detail).

Since the corpus is tiny (5-10 items) both approaches will return sensible
top-k results — this isn't a scenario requiring embedding quality at scale,
just needs to reliably retrieve "the brute-force excerpt" when the query is
about brute force.

---

## Step 4 — Confidence score, honestly

Whatever specific number appears on the threat card (e.g. "91%"), it must
come from the Risk Assessor's actual formula, not be hardcoded for demo
polish. Judges may ask "how is that number calculated" — have a real
answer. It's fine for the formula to be simple (e.g. normalized weighted
sum of a few signals) as long as it's real and consistent.

---

## Step 5 — API surface

- `POST /analyst/analyze` — runs the pipeline up through Response Planner,
  returns the threat card + recommended actions
- `POST /analyst/approve-response` — triggers Human Approval →
  Simulation Action → Environment Updated, returns updated graph/event state
- `GET /analyst/rag-sources` — optional, lets the frontend show "evidence
  sources used" with links

---

## Checkpoint — what should work at the end of this file

Running the full `01` scenario through this pipeline (with `USE_LLM=false`,
the default) produces, with no network calls:

- A correctly categorized threat (`credential_brute_force` → account
  compromise → priv-esc → DB access)
- A severity and confidence score you can trace back to the scoring formula
- 2-3 evidence excerpts from the RAG corpus, correctly matched to the
  category, with source citations
- An attack path pulled from the real graph query, not hardcoded text
- An ordered response plan with reasons
- After a simulated "approve," graph/event state visibly reflects
  containment

---

## You must be able to explain

- The exact rule/threshold in Threat Detector that flags this specific
  scenario, and why it wouldn't false-positive on normal traffic
- How the confidence score is calculated — walk through the formula on the
  actual numbers from a real run
- Why Human Approval blocks execution rather than the AI acting
  autonomously — connect this to "why is this responsible AI design for a
  security tool"
- How the RAG fallback works and why the demo never depends on the
  embedding model or any external API being reachable
- What would change in this pipeline if you added a real LLM key —
  precisely which nodes get richer, which stay identical
