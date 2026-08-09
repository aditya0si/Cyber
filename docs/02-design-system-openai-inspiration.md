# 02 — Design System (OpenAI-inspired, adapted for CyberSim AI)

> **Inspiration, not imitation.** We reverse-engineer the *visual language* of OpenAI's products (platform.openai.com and ChatGPT) because it is the gold standard for dense, trustworthy, low-glare professional tools used to read a lot of text. We do **not** copy OpenAI's logo, wordmark, brand marks, copy tone, or proprietary assets. CyberSim AI has its **own** identity, tuned toward a security operations product: a restrained neutral base with semantic severity colors.

---

## 1. Why OpenAI's UI as the reference (and what we take vs. leave)

OpenAI's products exemplify a set of properties we want:

| Property | What OpenAI does well | What CyberSim takes | What CyberSim changes |
|----------|----------------------|---------------------|----------------------|
| **Color restraint** | Near-monochrome UI; color is meaning (status), never decoration. | Yes — neutral base, color only for severity/state. | Add a 4-step **severity ramp** (info/low/medium/high/critical) since SOC tools live and die by it. |
| **Text-forward** | Content is the hero; chrome recedes. | Yes — events/detections as readable prose-like rows. | Add **monospace technical density** (event IDs, MITRE IDs, CVEs, IPs) — more code-like UI than OpenAI. |
| **Dark-first** | platform.openai.com is dark by default; ChatGPT supports both. | Yes — dark is primary; light is first-class. | Provide a true, design-checked light theme (not auto-generated). |
| **Subtle borders** | 1px borders at low-opacity white; cards are quiet. | Yes. | Use slightly higher border contrast for data-dense tables (legibility). |
| **Rounded but not toyish** | Radii ~8–16px; balanced, not "all 2xl." | Yes — a 3-step radius scale. | Data tables use smaller radii (4–6px) for precision feel. |
| **Restful motion** | 120–200ms transitions; no bounce on functional UI. | Yes — functional motion only. | Add purposeful motion for streaming events (progressive reveal) where it aids comprehension. |
| **Consistent verb labels** | terse, lowercase-ish action buttons. | Yes. | Keep; security UIs need crisp actions (`Block IP`, `Quarantine`, `Rotate`). |

> **Self-question:** Is cloning OpenAI's look the best approach for a *security* product whose main panel is a SOC dashboard — a layout OpenAI doesn't ship? **Answer:** No. We adopt the *tokens, density, restraint, and motion language*, but the SOC dashboard layout is closer to a security console (this is where we diverge — see §15 "Layout patterns: SOC Dashboard"). The product's primary surfaces (chat composer, event rows, code blocks, tables, sidebars) closely track OpenAI's because that vocabulary is what professional users trust.

---

## 2. Identity

- **Product name:** CyberSim AI
- **Wordmark:** `CyberSim` in display weight + `AI` in a muted accent weight. Do not stylize as a logo faker of any existing company.
- **Logo mark (mark):** A simple monoline glyph evoking a graph node with edges (a hub-and-spoke). Single stroke, 1.5px, currentColor. Provided as SVG in `apps/web/public/mark.svg`. *(TBD by design pass; placeholder spec: 24×24 viewBox, 3 nodes, 2 edges.)*
- **Voice:** Technical, calm, never alarmist. Severity is conveyed by color and label, not exclamation or emoji.

## 3. Design tokens

Tokens are consumed as CSS custom properties (`--cs-*`) generated from a Tailwind v4 config and a `tokens.css`. Both dark and light themes are defined; **dark is the default**. Tailwind v4 ships a token-first config (`@theme`), so we keep a single source in `apps/web/src/styles/tokens.css` and map Tailwind colors to them.

### 3.1 Color — Neutral ramps (dark-first)

```css
:root[data-theme="dark"] {
  /* Surfacedace/backdrop */
  --cs-neutral-0:  #0a0a0b;  /* app bg (deepest)             */
  --cs-neutral-1:  #0f1011;  /* sidebar / panel bg            */
  --cs-neutral-2:  #16181b;  /* card bg                       */
  --cs-neutral-3:  #1c1f23;  /* raised card / hover bg        */
  --cs-neutral-4:  #24282d;  /* input bg / active pill bg     */
  --cs-neutral-5:  #2e3339;  /* table header bg               */
  --cs-neutral-6:  #3a4047;  /* disabled bg                   */
  /* borders */
  --cs-border-subtle: rgba(255,255,255,0.06);
  --cs-border-default: rgba(255,255,255,0.10);
  --cs-border-strong:  rgba(255,255,255,0.16);
  --cs-border-focus:   rgba(255,255,255,0.32);
}
```

```css
:root[data-theme="light"] {
  --cs-neutral-0:  #ffffff;
  --cs-neutral-1:  #f7f8f9;
  --cs-neutral-2:  #ffffff;   /* cards on panel bg */
  --cs-neutral-3:  #f1f3f5;
  --cs-neutral-4:  #e9ecee;
  --cs-neutral-5:  #e3e6e9;
  --cs-neutral-6:  #d4d9dd;
  --cs-border-subtle: rgba(0,0,0,0.06);
  --cs-border-default: rgba(0,0,0,0.10);
  --cs-border-strong:  rgba(0,0,0,0.16);
  --cs-border-focus:   rgba(0,0,0,0.30);
}
```

#### Text on neutrals
```css
:root[data-theme="dark"] {
  --cs-text-primary:   #F4F4F5;  /* 13.8:1 on neutral-2 */
  --cs-text-secondary: #B8BCC2;
  --cs-text-tertiary:  #8A9098;
  --cs-text-quaternary:#626a72;
  --cs-text-inverse:   #0a0a0b;  /* text on accent fills */
}
:root[data-theme="light"] {
  --cs-text-primary:   #0f1011;
  --cs-text-secondary: #475063;
  --cs-text-tertiary:  #6b7480;
  --cs-text-quaternary:#8b9099;
  --cs-text-inverse:   #ffffff;
}
```
> All text/on-bg pairings must reach **≥ 4.5:1** (AA) for body and **≥ 3:1** for non-essential text ≥ 18px bold. Token choices above verified against `--cs-neutral-2`. The CI accessibility gate (§16) re-computes these from computed styles to prevent regressions.

### 3.2 Color — Semantic (severity & state)

Severity is the heart of a SOC UI. These ramps must be perceptually distinct in **both** themes and colorblind-safe (tested against deuteranopia/protanopia). Use **Okabe-Ito-adjacent** hues + a red/amber/green/blue/violet five-category palette.

```css
:root[data-theme="dark"] {
  /* Severity (used for detections, badges, dots, edges on graph) */
  --cs-sev-info-fg:     #6EA8FE; --cs-sev-info-bg:     rgba(110,168,254,0.12);
  --cs-sev-low-fg:      #7CD1A6; --cs-sev-low-bg:      rgba(124,209,166,0.12);
  --cs-sev-medium-fg:   #E7C66B; --cs-sev-medium-bg:  rgba(231,198,107,0.12);
  --cs-sev-high-fg:     #F39560; --cs-sev-high-bg:     rgba(243,149,96,0.12);
  --cs-sev-critical-fg: #FD6A6A; --cs-sev-critical-bg:rgba(253,106,106,0.14);
  /* State */
  --cs-ok-fg:    #7CD1A6; --cs-ok-bg:    rgba(124,209,166,0.12);
  --cs-warn-fg:  #E7C66B; --cs-warn-bg:  rgba(231,198,107,0.12);
  --cs-error-fg: #FD6A6A; --cs-error-bg: rgba(253,106,106,0.14);
}
:root[data-theme="light"] {
  --cs-sev-info-fg:     #1E63B8; --cs-sev-info-bg:     rgba(30,99,184,0.10);
  --cs-sev-low-fg:      #1E7A57; --cs-sev-low-bg:      rgba(30,122,87,0.10);
  --cs-sev-medium-fg:   #8A6500; --cs-sev-medium-bg:  rgba(138,101,0,0.12);
  --cs-sev-high-fg:     #BC4B14; --cs-sev-high-bg:     rgba(188,75,20,0.10);
  --cs-sev-critical-fg: #C02020; --cs-sev-critical-bg: rgba(192,32,32,0.10);
  --cs-ok-fg:    #1E7A57; --cs-ok-bg:    rgba(30,122,87,0.10);
  --cs-warn-fg:  #8A6500; --cs-warn-bg:  rgba(138,101,0,0.12);
  --cs-error-fg: #C02020; --cs-error-bg: rgba(192,32,32,0.10);
}
```
> **Self-question:** Five severity levels on a near-monochrome base still readable for colorblind users? **Answer:** Severity is **never color-only**. Every severity marker carries a **label** and a **glyph dot** with distinct shape/icon (info: ○, low: ◇, medium: ▽ high: △, critical: ✕-hexagon). Color is reinforcement, not the sole carrier. This is also WCAG-safe and resolves the long-standing "red vs green" problem on SEVs.

### 3.3 Color — Accent

A single restrained accent for primary actions, focus rings, selected items, and the AI analyst's "reasoning" highlights.

```css
:root[data-theme="dark"] {
  --cs-accent-fg:        #79E0B0;          /* mint — associates with "AI analyst" */
  --cs-accent-fg-hover: #5FCB97;
  --cs-accent-bg:        #11241c;          /* surfaces with mint tint        */
  --cs-accent-ring:      rgba(121,224,176,0.55);
}
:root[data-theme="light"] {
  --cs-accent-fg:        #0E7C52;
  --cs-accent-fg-hover:  #0A6644;
  --cs-accent-bg:        #E6F7EF;
  --cs-accent-ring:      rgba(14,124,82,0.45);
}
```
> **Self-question:** Mint accent for a security product — appropriate, or too playful? **Answer:** Appropriate *at this saturation*. It reads as "the analyst's signature" and is distinctly non-red/non-amber, so it never collides with severity. We deliberately avoid blue accent (too generic, clashes with sev-info). Mint also nods to terminals/green-screens, which resonates with security practitioners.

### 3.4 Typography

```css
:root {
  --cs-font-sans:  "Söhne", "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Inter, sans-serif;
  --cs-font-serif: ui-serif, Georgia, Cambria, "Times New Roman", serif;       /* not used in product UI */
  --cs-font-mono:  "SF Mono", ui-monospace, "JetBrains Mono", "Fira Code", Menlo, Consolas, monospace;
}
```
- **Primary typeface:** Inter (open-source, ships with fontsource; fallback when Söhne unavailable). *Söhne is OpenAI's licensed face — we do not ship it; Inter is the visually closest open alternative for body/UI.*
- **Mono:** JetBrains Mono for codespan/identifiers (event IDs, MITRE IDs, CVEs, IPs, JSON).
- Use **`font-feature-settings: "cv11", "ss03"`** to slim Inter's digits for tables.

#### Type scale (rem, 1rem=16px)
| Token | Size / LH | Weight | Use |
|-------|-----------|--------|-----|
| `text-xs`    | 12px / 1.45 (16) | 400/500 | badges, table dense, captions |
| `text-sm`    | 13px / 1.5 (20)  | 400     | body default in dense UI |
| `text-base`  | 14px / 1.55 (22) | 400     | default body in marketing & chat |
| `text-md`    | 15px / 1.6 (24)  | 500     | row titles, event summaries |
| `text-lg`    | 18px / 1.4 (25)  | 600     | section headers, modal titles |
| `text-xl`    | 20px / 1.35 (27) | 600     | panel H2 |
| `text-2xl`   | 24px / 1.3 (31)  | 600     | H1 inner |
| `text-3xl`   | 30px / 1.25 (38) | 700     | LCP-hero, mission title |
| `text-4xl`   | 36px / 1.2 (43)  | 700     | marketing hero only |

> Note deviations from Tailwind defaults (`text-sm`=14px, `text-base`=16px). SOC UX skews slightly smaller than marketing; the same scale applies but the **default body in the dashboard is `text-sm` (13px)**, not `text-base`. Marketing uses `text-base`+. This keeps density high in console and airiness in marketing.

### 3.5 Spacing scale
`0,1,2,3,4,5,6,8,10,12,14,16,20,24,32,40,48,64,80,96` (px) → Tailwind utility classes. **8px grid**; 4px allowed for inline gaps inside rows/cards. Gutters: 16px mobile, 24px tablet, 32px desktop, capped at 1200px content width.

### 3.6 Radius scale
| Token | Radius | Use |
|-------|--------|-----|
| `radius-xs` | 4px | badges, inline code chips, table mock themselves |
| `radius-sm` | 6px | inputs, buttons (compact), table cells |
| `radius-md` | 8px | cards (default), buttons (default) |
| `radius-lg` | 12px | raised cards, modals, panels |
| `radius-xl` | 16px | hero cards, chat composer pill |
| `radius-full` | 9999px | dots, status pills, icon-only buttons |

> Self-question: OpenAI uses fairly soft radii (~12–16px) on cards; is our `md:8px` too tight for them? **Answer:** For marketing/hero surfaces we use `lg/xl` (12–16) — matches the reference. For dense panels we drop to `md:8px` because heavy softness on stacked rows reads as "toy." This is an intentional, sitested divergence.

### 3.7 Elevation (shadows) — dark theme prefers borders over shadows
```css
:root[data-theme="dark"] {
  --cs-shadow-1: 0 1px 0 rgba(255,255,255,0.04) inset;                          /* card edge */
  --cs-shadow-2: 0 1px 2px rgba(0,0,0,0.5), 0 0 0 1px var(--cs-border-default);
  --cs-shadow-3: 0 12px 32px rgba(0,0,0,0.55), 0 0 0 1px var(--cs-border-default); /* modals */
  --cs-overlay:  rgba(0,0,0,0.55);
}
:root[data-theme="light"] { /* shadows carry more load in light */
  --cs-shadow-1: 0 1px 2px rgba(15,16,17,0.04);
  --cs-shadow-2: 0 2px 6px rgba(15,16,17,0.08), 0 0 0 1px var(--cs-border-default);
  --cs-shadow-3: 0 16px 40px rgba(15,16,17,0.14), 0 0 0 1px var(--cs-border-default);
  --cs-overlay:  rgba(8,9,11,0.40);
}
```

### 3.8 Motion
```css
:root {
  --cs-ease-out:   cubic-bezier(0.22, 1, 0.36, 1);
  --cs-ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
  --cs-dur-1: 120ms;  /* micro: hover, focus    */
  --cs-dur-2: 180ms;  /* small: toggles, chips   */
  --cs-dur-3: 260ms;  /* panel: drawers, modals  */
  --cs-dur-4: 400ms;  /* scene: route transition */
}
```
- **No bounce / spring on functional UI.** Only `--cs-ease-out` for entrances.
- **Streaming reveal:** new events fade/translate in 120ms (`translateY(4px)→0`, opacity 0.4→1) as they append; capped so a burst never thrashes (max 16fps reveal).
- **`prefers-reduced-motion`** disables non-essential motion and replaces reveal with instant-append. **Normative.**
- Loading skeleton shimmer uses slow 1.4s linear loop, opacity 0.6↔1.0 on `--cs-neutral-3`.

### 3.9 Density
- Three density modes: **Comfortable (16px row)**, **Compact (12px row)**, **Ultracompact (8px row, monospace)**. Persist per user. Default: Comfortable for SOC dashboard rows, Compact for tables. Toggle in user menu. SOC operators ~ love density.

### 3.10 Focus & keyboard
```css
--cs-ring: 0 0 0 2px var(--cs-neutral-2), 0 0 0 4px var(--cs-accent-ring);
```
- Visible focus on **every interactive element.** Never remove outline without replacing.
- All actions keyboard-reachable; logical tab order matches visual order.
- `Cmd/Ctrl+K` opens global command palette (`13`).
- `?` toggles keyboard shortcut help.

---

## 4. Component inventory (mapping to ChatGPT/platform vocabulary)

Each component spec lists: purpose, anatomy, variants, states, motion, a11y notes, and the App-Router file that implements it. (File paths are normative; see `13-frontend-architecture.md`.)

### 4.1 Layout shell — `AppShell`  `apps/web/src/components/shell/AppShell.tsx`
- Persistent **left sidebar** (collapsed to icon rail at <1024px; hidden in Mission Mode theater). Content scroll, sidebar fixed. Mirrors ChatGPT shell.
- **Top bar** (44px): wordmark-left when sidebar collapsed, breadcrumb center, density/right cluster (theme toggle, env badge, notifications, user menu).
- Surfaces in `apps/web/src/app/(dashboard)/layout.tsx`.

### 4.2 Sidebar — `Sidebar`  `…/shell/Sidebar.tsx`
- 256px expanded, 56px collapsed. Items: Scenario Library, New Simulation, SOC Dashboard, Missions, Attack Graph, Knowledge, Settings.
- Section grouping (SIMULATION / ANALYSIS / ORG). Active item: `--cs-accent-bg`, `--cs-accent-fg` text, 2px accent bar on the left inside the item.
- Bottom: workspace switcher + usage meter (`16`).

### 4.3 Event row — `EventRow`  `…/dashboard/EventRow.tsx`
The atomic unit of the live feed. Anatomy: severity dot+glyph · timestamp (mono `text-xs`) · source (svc + IP, mono, muted) · event-type chip · one-line summary (`text-sm`) · expand chevron.
- States: unread (left 2px sev bar), hover (raise bg), selected (accent-faint bg), streaming-in (motion §3.8).
- Expand reveals: raw structured payload (JSON, mono, syntax-highlighted), related events, MITRE tactic/technique tags, **"Why did the AI flag this?"** affordance that scrolls the linked Detection into view.

### 4.4 Detection card — `DetectionCard`  `…/dashboard/DetectionCard.tsx`
At the top of the analyst stream. Reproduces the AI package (see `11` §5):
```
┌ THREAT DETECTED · credential_compromise · HIGH · ━━━━━━━━━━ 91% ━━━━━━━━ |
│ Confidence: 91%
│ Evidence
│  • repeated_failed_logins (17 events)  [→ view]
│  • successful_login_from_new_location  [→ view]
│  • privilege_escalation                 [→ view]
│ Attack path: Internet → API → Auth endpoint → Database  [→ graph]
│ AI rationale (expandable, ≤ 600 chars):
│   "17 anomalous requests from 203.0.113.42 within 4s, SQL metacharacters
│    present, correlated DB errors, sudden widen of query results…"
│ Recommended response
│  1. Block source IP        2. Rate-limit /login   3. Disable endpoint
│  4. Rotate credentials    5. Inspect DB logs
│ [ Execute response ▸ ]   [ Ask follow-up ]
│ References: MITRE T1110 (Brute Force), OWASP A07:2021, CVE-…(if linked)
└────────────────────────────────────────────────────────────────────────── |
```
- Severity chip + glyph from §3.2. Confidence as **5-segment bar**, not a single number (faster to scan).
- Each evidence item is a deep link that opens the referenced events in the feed (multi-select highlights them) and on the graph.
- **No detection without evidence.** Component refuses to render a Detection lacking ≥1 evidence item; this is enforced by the backend DTO and reinforced by the validator in `11`.

### 4.5 Attack graph view — `GraphView`  `…/dashboard/GraphView.tsx`
- Force-directed SVG/Canvas hybrid (see §15 + `10`). Nodes colored by asset type; compromised nodes flash the severity glyph; edges colored by traversal (recon: dashed info, foothold: solid high, lateral: solid critical).
- Mini-map + filter chips (asset types, attack stages) + time scrubber that replays graph state across event time.
- Click a node → side drawer with asset detail, connections, current foothold status, MITRE-centric technique tags.

### 4.6 Chat composer — `AskAnalyst`  `…/dashboard/AskAnalyst.tsx`
- Reproduces ChatGPT's composer language: a **pill-shaped** input (`radius-xl`), placeholder *"Ask the analyst… (e.g., 'why is 203.0.113.42 suspicious?')"*.
- Shift+Enter newline, Enter submit, attachments chip (references: pinned events, detections, graph nodes) appended above the input.
- The analyst replies are **answer cards** with the same structure as DetectionCards where applicable; all claims carry footnoted evidence refs.
- **Streaming** token-by-token render only for the prose `rationale` field; structured fields render atomically (no half-confidence numbers).

### 4.7 Code/JSON block — `CodeBlock` `…/ui/CodeBlock.tsx`
- Mono, `text-xs`, `radius-sm`, copy button top-right (8px inset), line numbers off by default (toggle), syntax highlight via Shiki (shared grammar: JSON, SQL, HTTP, bash, mermaid). Used everywhere technical text appears.
- Long blocks collapse to 200px with "Expand" (so dense event payloads don't dominate the screen).

### 4.8 Status dot — `StatusDot` `…/ui/StatusDot.tsx`  + `SeverityGlyph`
Severity = color + shape glyph (§3.2). Dot 8px; glyph 14px. Used in tables, feed, graph nodes.

### 4.9 Buttons — `Button` `…/ui/Button.tsx`
Variants: `primary` (accent fill, inverse text), `secondary` (transparent + default border), `ghost` (transparent, hover bg), `danger` (critical fill). Sizes: `sm`(28px)/`md`(36px)/`lg`(44px). Icon-only buttons (`radius-full`). Loading: inline spinner (12px), keep label.
> Verb labels are **terse title-case action verbs**: `Block IP`, `Execute response`, `Rotate credentials` — never "Submit" / "Click here."

### 4.10 Tables — `DataTable` `…/ui/DataTable.tsx`
- Sticky header, zebra off, row hover = `--cs-neutral-3`, sortable, server-side pagination via cursor for large event stores. Compact density default (12px row).
- Cell renderers: `MonoCell`, `SevCell`, `RelativeTimeCell`, `JSONCell` (truncated + expand).

### 4.11 Toasts — `Toast` `…/ui/Toast.tsx`
Bottom-right, 360px, `radius-lg`, auto-dismiss 5s (errors sticky until dismissed). Severity-tinted left bar.

### 4.12 Modal/Drawer — `Modal`, `Drawer` `…/ui/Modal.tsx`
- Drawer slides from right (380px default, 560px wide option), `--cs-dur-3`. Modals center, backdrop `--cs-overlay`.Both support `Esc` close, focus-trap, return-focus.

### 4.13 Command palette — `CmdK` `…/ui/CmdK.tsx`
- `Cmd/Ctrl+K`. Searches: scenarios, simulations, detections, missions, graph nodes, knowledge entries. Quick actions (toggle theme, density, start scenario, mute alerts). kbar-based or Radix Cmdk.

### 4.14 Mission theater — `MissionStage` `…/mission/MissionStage.tsx`
- Full-bleed presentation mode (sidebar hidden) for live demos. Big mission title, objective checklist left, event ticker center, AI analyst summary pinned right, **EXECUTE RESPONSE** giant glowing button. Theatrical but disciplined. See `14`.

---

## 5. Layout patterns

### 5.1 Three-pane console — `SOC Dashboard` (primary product surface)
```
┌─────────┬──────────────────────────────┬───────────────────┐
│ LEFT    │ CENTER                       │ RIGHT             │
│ feed    │ analyst + graph (tabbed)     │ inspector + actions│
│ 320px   │ flex                          │ 360px             │
└─────────┴──────────────────────────────┴───────────────────┘
```
- **Left:** live event feed (`DataTable` + streaming `EventRow`). Filter chips (severity, source, type) collapsed above.
- **Center:** tabbed — `Analyst` (DetectionCards + AskAnalyst) and `Attack Graph` (`GraphView`). The hero of the dashboard.
- **Right:** Inspector — context for the selected event/detection: raw payload, related events, graph node, MITRE tags, evidence trail, and the Response Console (`Execute response`, responses pending, executed actions with timestamps).
- Collapses responsibly: <1280px → right pane becomes a `Drawer`; <880px → center feed takes over, analyst folds below.

> **Self-question:** Three panes is dense — is it the right call vs. a simpler two-pane (feed + detail)? **Answer:** The product thesis is "AI explains and recommends responses." Splitting *what's happening* (left), *what the AI thinks* (center), and *what we do about it* (right) into three persistent panes makes the thesis spatially literal. We mitigate density via density modes + collapse rules + reclari of contents (single source of truth pane). This is the deliberate divergence from ChatGPT's single-column; ChatGPT solves reading, we solve triage.

### 5.2 Marketing/site layouts (`apps/web/src/app/(marketing)/*`)
- Centered 1200px content, generous vertical rhythm (24px → 48px between sections), hero with `text-3xl`/`4xl`, feature grid (3-col), code-window hero showing the JSON decision package (the architecture slide as a real artifact). These are airy; the contrast with the dense console is the point.

### 5.3 Mission theater
- Full-screen, 12-column overlay grid, `radius-xl` cards, animated objective completion checks, big confidence bar. Auto-advances scenes when `autoplay` is enabled (judge-driven by default).

---

## 6. Iconography
- **Lucide** icon library (open-source, MIT; matches OpenAI's stroke-1.5 line aesthetic). Stroke 1.5px, size 16/20px for UI; 24px in command palette.
- Stroken geometric, no fills; severity uses our own glyph set (§3.2).
- Status glyphs are custom inline SVG (per the shape encoding rule).

---

## 7. Accessibility (WCAG 2.2 AA — normative)

1. **Severity is never color-only** (label + glyph).
2. All interactive elements: visible focus, min 24×24px target (44px on mobile critical).
3. Color contrast: body ≥ 4.5:1; large + non-essential ≥ 3:1; verified by CI axe-core + a computed-style audit script (see `20`).
4. `prefers-reduced-motion` honored globally (§3.8).
5. `prefers-color-scheme` sets initial theme, persisted after user choice (default dark per OpenAI parity).
6. Live event feed: `aria-live="polite"` with a 250ms debounce so bursts don't flood SR; visible counter announces "N new events" via a visually-hidden polite region.
7. Streaming JSON viewer: keep DOM additions batched (≤8/sec to AT) by rendering older events into static DOM segments past 32 visible.
8. Keyboard map documented and discoverable (`?`).
9. Motion of graph respects reduced-motion (instant layout, no animation).
10. Workspace saving respect for users with `prefers-contrast: more` (raises `--cs-border-default` to `--cs-border-strong`).

---

## 8. Tailwind v4 integration sketch
- `apps/web/tailwind.config.ts` (v4 `@theme` inline) maps `cs-*` generators:
    - backgroundColor: `bg-cs-neutral-{0..6}`, `bg-cs-accent`, `bg-cs-sev-{sev}`
    - borderColor: `border`, plus `border-cs-default/subtle/strong`
    - textColor: `text-cs-primary/secondary/tertiary/quaternary`, `text-cs-sev-{sev}-fg`
    - radius: `rounded-cs-{xs..xl}`
- One directive: `@import "tailwindcss"; @import "../styles/tokens.css";`
- **No ad-hoc hex** in components. CI grep fails build on raw `#` literals in `apps/web/src/**` outside `tokens.css` and `tailwind.config.ts` (see `20`).

---

## 9. Decision rationale & alternatives recap

| Decision | Chosen | Rejected | Why |
|----------|--------|----------|-----|
| Reference language | OpenAI (ChatGPT + platform) | Vercel, Linear, GitHub dark | OpenAI best marries density + text-forward + restraint; closest to "trustworthy pro tool." |
| Dark-first | Yes | Light-first | Matches reference + SOC convention + reduces glare on analysts' long sessions. |
| Severity encoding | Color + label + glyph (5 levels) | Color only / 3 levels | Colorblind-safe; SOC needs 5 levels; recovers the "every severity is meaningful" property. |
| Accent | Mint | Blue | Avoid generic + avoid clash with sev-info. |
| Framework/utility approach | Tailwind v4 + CSS vars | Styled-components / unstyled headless only | Tokens + utilities match component density; CSS vars enable runtime theming (dark/light/density) with zero rebuild. |
| Type | Inter + JetBrains Mono (open) | Söhne (closed) / system | Open, accessible, visually close; no licensing entanglement. |
| 3-pane dashboard | Yes | Single ChatGPT column | Triage is the job; axes (events / analysis / action) deserve space. Marketing stays airy to contrast. |
| Motion library | none (CSS only) | Framer Motion / GSAP | Functional motion is small; CSS var easings suffice; smaller bundle. *Optional:* Framer Motion ONLY for Mission theater scene transitions. |

---

End of `02-design-system-openai-inspiration.md`. Next: `03-system-architecture.md`.
